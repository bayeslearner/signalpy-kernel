"""Run the examples from README.md and the guide, and check their claims.

Written because the README once showed `return ctx.server.add_route(...)` with
the comment "returns its undo". No such API exists — a plain class's method
returns whatever its author wrote. The docs had invented a capability, which is
the worst kind of documentation bug: it teaches a mental model the code does not
have.

If an example changes, change it here too. If it stops being runnable, this
fails.
"""

import asyncio

from plugkit import Context, provide


async def settle(n=10):
    for _ in range(n):
        await asyncio.sleep(0)


# ── the quickstart ────────────────────────────────────────────────────────


class Database:
    def __init__(self, dsn="sqlite://"):
        self.dsn = dsn
        self.closed = False

    def close(self):
        self.closed = True


class Greeter:
    def __init__(self, database, prefix="hello"):
        self.database = database
        self.prefix = prefix

    def hello(self, name):
        return f"{self.prefix} {name}"


async def test_quickstart():
    root = Context()
    await root.plugin(provide(Database, "database"))
    await root.plugin(provide(Greeter, "greeter", needs=["database"]))
    await settle()
    assert root.greeter.hello("world") == "hello world"


# ── "The one idea", steps 1-5 ─────────────────────────────────────────────


class Server:
    """Step 1. Ordinary Python. plugkit does not know what a route is."""

    def __init__(self):
        self.routes = {}

    def add_route(self, path, handler):
        self.routes[path] = handler

    def remove_route(self, path):
        self.routes.pop(path, None)


async def test_step3_inject_is_a_precondition():
    """Mounted before its dependency exists, the plugin waits rather than fails."""
    from plugkit import FiberState

    def admin_api(ctx, config=None):
        ctx.server.add_route("/admin", lambda: "admin page")

    admin_api.inject = ["server"]

    root = Context()
    fiber = root.plugin(admin_api)
    await settle()
    assert fiber.state is FiberState.PENDING
    assert "server" not in root

    await root.plugin(provide(Server, "server"))
    await settle()
    assert fiber.state is FiberState.ACTIVE
    assert list(root.server.routes) == ["/admin"]


async def test_step3_ctx_server_is_just_the_instance():
    """No wrapper, no proxy semantics the reader has to learn."""
    root = Context()
    await root.plugin(provide(Server, "server"))
    await settle()
    assert isinstance(root.server, Server)
    assert isinstance(root.server.routes, dict)
    assert root.server is root["server"]


async def test_step4_the_route_survives_unload():
    """The claim the whole section rests on."""

    def admin_api(ctx, config=None):
        ctx.server.add_route("/admin", lambda: "admin page")

    admin_api.inject = ["server"]

    root = Context()
    await root.plugin(provide(Server, "server"))
    fiber = await root.plugin(admin_api)
    await settle()
    assert list(root.server.routes) == ["/admin"]

    await fiber.dispose()
    await settle()
    assert list(root.server.routes) == ["/admin"], "the README's problem does not reproduce"


async def test_step5_returning_the_undo_fixes_it():
    def admin_api(ctx, config=None):
        ctx.server.add_route("/admin", lambda: "admin page")
        return lambda: ctx.server.remove_route("/admin")

    admin_api.inject = ["server"]

    root = Context()
    await root.plugin(provide(Server, "server"))
    fiber = await root.plugin(admin_api)
    await settle()
    assert list(root.server.routes) == ["/admin"]

    await fiber.dispose()
    await settle()
    assert list(root.server.routes) == []


async def test_step5_effects_run_in_reverse():
    order = []

    def admin_api(ctx, config=None):
        def route(path, handler):
            def install():
                ctx.server.add_route(path, handler)
                order.append(f"add {path}")
                return lambda: (ctx.server.remove_route(path), order.append(f"remove {path}"))
            return install

        ctx.effect(route("/admin", lambda: "admin"))
        ctx.effect(route("/health", lambda: "ok"))

    admin_api.inject = ["server"]

    root = Context()
    await root.plugin(provide(Server, "server"))
    fiber = await root.plugin(admin_api)
    await settle()
    assert sorted(root.server.routes) == ["/admin", "/health"]

    await fiber.dispose()
    await settle()
    assert root.server.routes == {}
    assert order == ["add /admin", "add /health", "remove /health", "remove /admin"]


async def test_unload_also_happens_when_the_dependency_is_replaced():
    """The README claims the fiber covers unload paths a try/finally does not."""
    removed = []

    def admin_api(ctx, config=None):
        ctx.server.add_route("/admin", lambda: "admin page")
        return lambda: removed.append("cleaned")

    admin_api.inject = ["server"]

    root = Context()
    server_fiber = await root.plugin(provide(Server, "server"))
    await root.plugin(admin_api)
    await settle()
    assert removed == []

    await server_fiber.dispose()          # nobody called dispose on admin_api
    await settle()
    assert removed == ["cleaned"], "the undo did not run when the dependency left"

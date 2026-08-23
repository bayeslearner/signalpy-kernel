"""POPO bindings — the component must stay a plain object.

The load-bearing test is `test_component_needs_no_kernel_at_all`: the classes in
this file import nothing from plugkit and are constructed directly. If that
ever stops being true, the design has failed.
"""

import asyncio
from typing import Protocol

import pytest

from plugkit import ConfigService, Context, ReactiveService
from plugkit.binding import provide, snake_case


async def settle(n=15):
    for _ in range(n):
        await asyncio.sleep(0)


# ── the components. Plain classes. No imports, no decorators, no base class. ──


class Database:
    def __init__(self, dsn="sqlite://"):
        self.dsn = dsn
        self.closed = False

    def query(self, sql):
        return f"{self.dsn}:{sql}"

    def close(self):
        self.closed = True


class Cache:
    def __init__(self):
        self.data = {}


class Greeter:
    def __init__(self, database, prefix="hello"):
        self.database = database
        self.prefix = prefix

    def hello(self, name):
        return f"{self.prefix} {name}"


class GreeterDeps(Protocol):
    database: Database
    cache: Cache


# ── tests ────────────────────────────────────────────────────────────────────


def test_component_needs_no_kernel_at_all():
    """Constructible and testable with no kernel in sight."""
    greeter = Greeter(database=Database(dsn="fake://"), prefix="hi")
    assert greeter.hello("world") == "hi world"
    assert greeter.database.query("SELECT 1") == "fake://:SELECT 1"


def test_snake_case_default_names():
    assert snake_case("Greeter") == "greeter"
    assert snake_case("HTTPClient") == "http_client"
    assert snake_case("MCPServerManager") == "mcp_server_manager"


async def test_provide_registers_and_injects():
    root = Context()
    await root.plugin(provide(Database, "database"))
    await root.plugin(provide(Greeter, "greeter", needs=["database"]))
    await settle()

    assert root.greeter.hello("world") == "hello world"
    assert root.greeter.database.query("SELECT 1") == "sqlite://:SELECT 1"


async def test_needs_dict_renames_the_kwarg():
    class Wrapper:
        def __init__(self, db):
            self.db = db

    root = Context()
    await root.plugin(provide(Database, "database"))
    await root.plugin(provide(Wrapper, "wrapper", needs={"db": "database"}))
    await settle()
    assert root.wrapper.db is not None


async def test_needs_protocol_derives_the_inject_list():
    """One Protocol drives both the runtime wiring and the type checker."""
    plugin = provide(Greeter, "greeter", needs=GreeterDeps)
    assert plugin["inject"] == ["cache", "database"]


async def test_binding_waits_for_its_dependency():
    root = Context()
    await root.plugin(provide(Greeter, "greeter", needs=["database"]))
    await settle()
    assert getattr(root, "greeter", None) is None, "activated without its dependency"

    await root.plugin(provide(Database, "database"))
    await settle()
    assert root.greeter.hello("x") == "hello x"


async def test_config_reaches_the_constructor():
    root = Context()
    await root.plugin(ConfigService, {"dict": {"db": {"dsn": "pg://prod"}}})
    await root.plugin(provide(Database, "database", config={"dsn": ("db.dsn", "sqlite://")}))
    await settle()
    assert root.database.dsn == "pg://prod"


async def test_config_default_when_key_is_absent():
    root = Context()
    await root.plugin(ConfigService)
    await root.plugin(provide(Database, "database", config={"dsn": ("db.dsn", "sqlite://")}))
    await settle()
    assert root.database.dsn == "sqlite://"


async def test_close_runs_on_unload():
    root = Context()
    fiber = await root.plugin(provide(Database, "database"))
    await settle()
    component = root.database
    assert component.closed is False

    await fiber.dispose()
    await settle()
    assert component.closed is True, "close() was not called on unload"


async def test_close_false_skips_teardown():
    root = Context()
    fiber = await root.plugin(provide(Database, "database", close=False))
    await settle()
    component = root.database
    await fiber.dispose()
    await settle()
    assert component.closed is False


async def test_named_close_method():
    class Server:
        def __init__(self):
            self.stopped = False

        def shutdown(self):
            self.stopped = True

    root = Context()
    fiber = await root.plugin(provide(Server, "server", close="shutdown"))
    await settle()
    server = root.server
    await fiber.dispose()
    await settle()
    assert server.stopped is True


async def test_bad_close_name_is_loud():
    class Thing:
        pass

    root = Context()
    with pytest.raises(AttributeError, match="nope"):
        await root.plugin(provide(Thing, "thing", close="nope"))


async def test_config_change_rebuilds_the_component():
    """A constructor argument cannot be mutated, so the binding restarts."""
    root = Context()
    await root.plugin(ReactiveService)
    await root.plugin(ConfigService, {"dict": {"db": {"dsn": "one://"}}})
    await root.plugin(provide(Database, "database", config={"dsn": ("db.dsn", "sqlite://")}))
    await settle()

    first = root.database
    assert first.dsn == "one://"

    root.config.set("db.dsn", "two://")
    await settle(40)

    assert root.database.dsn == "two://"
    assert root.database is not first, "the component was not rebuilt"
    assert first.closed is True, "the replaced component was not closed"


async def test_binding_works_without_reactive_mounted():
    """Reacting to config is opt-in; a minimal composition must still boot."""
    root = Context()
    await root.plugin(ConfigService, {"dict": {"db": {"dsn": "one://"}}})
    await root.plugin(provide(Database, "database", config={"dsn": ("db.dsn", "sqlite://")}))
    await settle()
    assert root.database.dsn == "one://"

    root.config.set("db.dsn", "two://")
    await settle()
    assert root.database.dsn == "one://", "rebuilt without ReactiveService mounted"


async def test_bad_needs_type_is_loud():
    with pytest.raises(TypeError, match="must be a list"):
        provide(Greeter, "greeter", needs=42)


# ── the @plugin decorator ────────────────────────────────────────────────


async def test_plugin_decorator_carries_inject():
    from plugkit.binding import plugin

    @plugin(inject=["database"])
    def uses_db(ctx, config=None):
        ctx.database.query("SELECT 1")

    assert uses_db["inject"] == ["database"]
    assert uses_db["name"] == "uses_db"

    root = Context()
    await root.plugin(provide(Database, "database"))
    await root.plugin(uses_db)
    await settle()


async def test_plugin_decorator_derives_inject_from_the_annotation():
    from plugkit.binding import plugin

    class Deps(Protocol):
        database: Database
        def on(self, event: str, listener: object) -> object: ...

    @plugin
    def reader(ctx: Deps, config=None):
        pass

    assert reader["inject"] == ["database"], "context methods leaked into inject"


def test_context_members_are_current():
    """CONTEXT_MEMBERS mirrors what cordis mixes onto a context. Catch drift."""
    from plugkit import Context
    from plugkit.binding import CONTEXT_MEMBERS

    root = Context()
    # timer members only exist when the timer plugin is mounted
    timer = {"timeout", "interval", "throttle", "debounce", "setTimeout", "setInterval"}
    missing = [name for name in CONTEXT_MEMBERS - timer if not hasattr(root, name)]
    assert not missing, f"listed as context members but absent from a real Context: {missing}"


# ── construction policy is a plugin, not the kernel ──────────────────────


async def test_a_rival_construction_policy_needs_no_kernel_change():
    """provide() registers one instance; provide_factory() registers a maker.

    Both are ordinary plugins touching the kernel through the same three
    methods. This is the answer to "is DI itself a plugin?" — the resolution
    and lifetime machinery is not, everything above it is.
    """
    from plugkit.examples.alternative_binding import provide_factory

    root = Context()
    await root.plugin(provide(Database, "database"))
    await root.plugin(provide_factory(Greeter, "greeter", needs=["database"]))
    await settle()

    first = root.greeter()
    second = root.greeter()
    assert first is not second, "a factory policy handed out a shared instance"
    assert first.hello("x") == "hello x"


async def test_a_factory_policy_still_unwinds_with_its_fiber():
    from plugkit.examples.alternative_binding import provide_factory

    root = Context()
    fiber = await root.plugin(provide_factory(Database, "db"))
    await settle()
    made = [root.db(), root.db()]
    assert not any(d.closed for d in made)

    await fiber.dispose()
    await settle()
    assert all(d.closed for d in made), "instances outlived the plugin that made them"


async def test_forgetting_the_service_name_is_a_hard_error():
    """No default name: it read as type-based injection and broke silently.

    Python raises before the body runs, which is the point — pyright catches it
    at author time rather than leaving a plugin that never activates.
    """
    with pytest.raises(TypeError, match="required positional argument"):
        provide(Database)


async def test_a_bad_service_name_says_what_to_pass():
    """The body's own check covers what Python's cannot: wrong type, or empty."""
    with pytest.raises(TypeError, match='provide\\(Database, "database"\\)'):
        provide(Database, "")
    with pytest.raises(TypeError, match="needs a service name"):
        provide(Database, 42)


async def test_the_service_name_is_the_link_not_the_class():
    """Renaming the class must not change the wiring."""

    class PostgresDatabase(Database):
        pass

    root = Context()
    await root.plugin(provide(PostgresDatabase, "database"))
    await root.plugin(provide(Greeter, "greeter", needs=["database"]))
    await settle()
    assert root.greeter.hello("x") == "hello x"


def test_the_public_surface_is_importable():
    """Everything the docs tell a reader to import must import.

    `plugin` was documented and not exported; `from plugkit import plugin`
    raised ImportError.
    """
    import plugkit

    for name in plugkit.__all__:
        assert hasattr(plugkit, name), f"{name} is in __all__ but not importable"

    from plugkit import Context, plugin, provide, bind, snake_case  # noqa: F401


def test_every_export_is_exercised_somewhere():
    """An export with no test is either public surface that needs one, or not
    public and should not be exported. This keeps that decision honest."""
    import pathlib
    import re

    import plugkit

    tests = " ".join(
        p.read_text() for p in pathlib.Path(__file__).parent.rglob("*.py")
    )
    untested = [n for n in plugkit.__all__ if not re.search(rf"\b{re.escape(n)}\b", tests)]
    assert not untested, f"exported but never used in a test: {untested}"

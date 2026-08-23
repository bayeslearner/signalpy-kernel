"""Run the examples from the guide chapters and assert what the prose claims.

Same reason as `test_readme_examples.py`: a documented API that does not exist is
the worst documentation bug, and the only defence is running what you wrote.
"""

import asyncio

import pytest

from plugkit import Context, FiberState, Service, plugin, provide


async def settle(n=15):
    for _ in range(n):
        await asyncio.sleep(0)


# ── chapter 4: writing your own service ──────────────────────────────────


class Routes(Service):
    provide = "routes"

    def __init__(self, ctx, config=None):
        super().__init__(ctx)
        self._table: dict = {}

    def add(self, path: str, handler: object):
        table = self._table

        def install():
            table[path] = handler
            return lambda: table.pop(path, None)

        return self.ctx.effect(install, f"routes.add({path!r})")

    def paths(self):
        return sorted(self._table)


async def test_a_registry_service_owns_registrations_by_caller():
    """The chapter's claim: unload the caller and its route disappears."""
    root = Context()
    await root.plugin(Routes)

    def admin(ctx, config=None):
        ctx.routes.add("/admin", "handler")

    admin.inject = ["routes"]
    fiber = await root.plugin(admin)
    await settle()
    assert root.routes.paths() == ["/admin"]

    await fiber.dispose()
    await settle()
    assert root.routes.paths() == [], "the route outlived the plugin that added it"


async def test_a_callable_held_as_service_data_is_not_rebound():
    """The hazard the chapter warns about, asserted rather than described."""

    class Approvals(Service):
        provide = "approvals"

        def __init__(self, ctx, config=None):
            super().__init__(ctx)
            self._answer = lambda question: f"answered {question}"

    root = Context()
    await root.plugin(Approvals)

    seen = []

    def caller(ctx, config=None):
        seen.append(ctx.approvals._answer("now?"))

    caller.inject = ["approvals"]
    await root.plugin(caller)
    await settle()
    assert seen == ["answered now?"], "the stored callable was rebound as a method"


# ── chapter 5: config and reactivity ─────────────────────────────────────


async def test_a_runtime_set_outranks_a_later_load(tmp_path):
    from plugkit import ConfigService

    other = tmp_path / "other.yml"
    other.write_text("http:\n  host: elsewhere\n")

    root = Context()
    await root.plugin(ConfigService, {"dict": {"http": {"timeout": 30}}})
    await settle()

    assert root.config.get("http.timeout") == 30
    assert root.config.get("http.retries", 3) == 3

    root.config.set("http.timeout", 60)
    root.config.load_yaml(str(other))
    assert root.config.get("http.timeout") == 60
    assert root.config.get("http.host") == "elsewhere"


async def test_an_effect_reruns_only_for_the_key_it_read():
    from plugkit import ConfigService, ReactiveService

    timeouts, hosts = [], []
    root = Context()
    await root.plugin(ReactiveService)
    await root.plugin(ConfigService, {"dict": {"http": {"timeout": 30, "host": "a"}}})
    await settle()

    def watcher(ctx, config=None):
        ctx.reactive.effect(lambda: timeouts.append(ctx.config.get("http.timeout")))
        ctx.reactive.effect(lambda: hosts.append(ctx.config.get("http.host")))

    watcher.inject = ["config", "reactive"]
    await root.plugin(watcher)
    await settle()

    root.config.set("http.timeout", 60)
    assert timeouts == [30, 60]
    assert hosts == ["a"], "an unrelated reader re-ran"


async def test_config_override_restores(tmp_path):
    from plugkit import ConfigService

    root = Context()
    await root.plugin(ConfigService, {"dict": {"http": {"timeout": 30}}})
    await settle()

    with root.config.override({"http": {"timeout": 1}}):
        assert root.config.get("http.timeout") == 1
    assert root.config.get("http.timeout") == 30


# ── chapter 7: testing ───────────────────────────────────────────────────


class FakeDatabase:
    def __init__(self):
        self.dsn = "fake://"


class Greeter:
    def __init__(self, database):
        self.database = database

    def hello(self, name):
        return f"hello {name}"


def test_a_component_is_testable_with_no_kernel():
    """The chapter's opening claim, and the reason provide() exists."""
    assert Greeter(database=FakeDatabase()).hello("world") == "hello world"


async def test_substituting_a_dependency_is_mounting_a_different_class():
    root = Context()
    await root.plugin(provide(FakeDatabase, "database"))
    await root.plugin(provide(Greeter, "greeter", needs=["database"]))
    await settle()

    assert root.greeter.database.dsn == "fake://"


async def test_observing_a_failure_without_awaiting():
    def might_fail(ctx, config=None):
        raise RuntimeError("no")

    root = Context()
    fiber = root.plugin(might_fail)

    with pytest.raises(RuntimeError):
        await fiber                      # waits for the transition, then re-raises
    assert fiber.state is FiberState.FAILED


async def test_a_failed_load_takes_three_ticks():
    """Why the guide says not to count ticks: LOADING -> UNLOADING -> FAILED."""
    seen = []
    root = Context()
    fiber = root.plugin(lambda ctx, config=None: (_ for _ in ()).throw(RuntimeError("no")))
    for _ in range(4):
        seen.append(fiber.state.name)
        await asyncio.sleep(0)
    assert seen == ["LOADING", "LOADING", "UNLOADING", "FAILED"], seen

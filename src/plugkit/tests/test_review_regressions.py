"""Regressions from the spec-03 review (S1-S12 / Q1-Q7 pass, 2026-08-23).

Each test failed when written. Keep them: all three are the kind of bug that
passes every feature test and shows up once, in production, on a bad day.
"""

import asyncio

import pytest

from plugkit import ConfigService, Context, ReactiveService, ToolsService
from plugkit.services.supervision import SupervisorService


async def settle(n=20):
    for _ in range(n):
        await asyncio.sleep(0)


def register(tool):
    def plugin(ctx, config=None):
        ctx.tools.register(tool)

    plugin.inject = ["tools"]
    return plugin


# ── Q1 CRITICAL — a tool body must run at most once ──────────────────────


def _helper(a, b):
    return a + b


class Destructive:
    """A tool whose body has an unrelated arity bug inside it."""

    name, description, parameters = "wipe", "deletes everything", {}

    def __init__(self):
        self.calls = 0

    def execute(self, arguments, execution=None):
        self.calls += 1
        return _helper(1, 2, 3)  # TypeError: takes 2 positional arguments but 3 given


async def test_a_tool_body_never_runs_twice():
    """The pipeline used to retry on TypeError to support 1-arg bodies.

    Any TypeError from *inside* the body that happened to mention positional
    arguments therefore re-invoked it — running a destructive side effect a
    second time, after the first had already happened.
    """
    tool = Destructive()
    root = Context()
    await root.plugin(ToolsService)
    await root.plugin(register(tool))
    await settle()

    result = await root.tools.execute("wipe")
    assert tool.calls == 1, f"the tool body ran {tool.calls} times"
    assert not result.ok and result.error["code"] == "TOOL_ERROR"


async def test_a_one_argument_tool_body_still_works():
    """The arity support the retry was there for, without the retry."""

    class Simple:
        name, description, parameters = "echo", "echoes", {}

        def execute(self, arguments):  # no `execution` parameter
            return arguments["text"]

    root = Context()
    await root.plugin(ToolsService)
    await root.plugin(register(Simple()))
    await settle()
    assert (await root.tools.execute("echo", {"text": "hi"})).value == "hi"


async def test_a_var_args_tool_body_works():
    class Flexible:
        name, description, parameters = "flex", "flexible", {}

        def execute(self, *args):
            return len(args)

    root = Context()
    await root.plugin(ToolsService)
    await root.plugin(register(Flexible()))
    await settle()
    assert (await root.tools.execute("flex")).value == 2


# ── Q1 HIGH — republish must not mutate its own iteration ────────────────


async def test_config_change_survives_a_reader_touching_a_new_key():
    """`_republish` iterated `self._keys` while notifying.

    A notified effect that reads a key nobody had read yet creates a Signal
    mid-iteration -> RuntimeError: dictionary changed size during iteration.
    """
    root = Context()
    await root.plugin(ReactiveService)
    await root.plugin(ConfigService, {"dict": {"a": 1}})
    await settle()

    seen = []

    def watcher(ctx, config=None):
        def body():
            if ctx.config.get("a") == 99:
                seen.append(ctx.config.get("discovered.later", "fallback"))

        ctx.reactive.effect(body)

    watcher.inject = ["config", "reactive"]
    await root.plugin(watcher)
    await settle()

    root.config.set("a", 99)  # used to raise
    assert seen == ["fallback"]


# ── Q1 HIGH — a supervisor must not restart itself ───────────────────────


async def test_one_for_all_excludes_the_supervisor():
    """`_siblings` matched on parent context, and the supervisor is a sibling.

    Restarting it wipes `_policies` and `_restarting`, so supervision silently
    stops for every fiber it was watching — during the incident it exists for.
    """
    root = Context()
    await root.plugin(SupervisorService)
    await settle()

    def flaky(ctx, config=None):
        raise RuntimeError("nope")

    fiber = root.plugin(flaky)
    await settle()

    targets = root.supervisor._targets(fiber, "one_for_all")
    names = [t.name for t in targets]
    assert "SupervisorService" not in names, f"supervisor would restart itself: {names}"
    assert "flaky" in names


async def test_supervision_survives_a_one_for_all_restart():
    root = Context()
    await root.plugin(SupervisorService)
    await settle()

    state = {"n": 0}

    def flaky(ctx, config=None):
        state["n"] += 1
        if state["n"] <= 1:
            raise RuntimeError("first attempt fails")

    fiber = root.plugin(flaky)
    await settle()
    root.supervisor.supervise(
        fiber, strategy="one_for_all", base_delay=0, backoff="constant"
    )
    fiber._error = None
    fiber.restart()
    await settle(40)

    assert root.supervisor.policy_for(fiber) is not None, "policy lost to a self-restart"


# ── axiom 5 — config.override was untested and malformed ─────────────────


async def test_config_override_restores_on_exit():
    root = Context()
    await root.plugin(ConfigService, {"dict": {"http": {"timeout": 30}}})
    await settle()

    assert root.config.get("http.timeout") == 30
    with root.config.override({"http": {"timeout": 1}}):
        assert root.config.get("http.timeout") == 1
    assert root.config.get("http.timeout") == 30


async def test_config_override_wakes_readers_both_ways():
    seen = []
    root = Context()
    await root.plugin(ReactiveService)
    await root.plugin(ConfigService, {"dict": {"http": {"timeout": 30}}})
    await settle()

    def watcher(ctx, config=None):
        ctx.reactive.effect(lambda: seen.append(ctx.config.get("http.timeout")))

    watcher.inject = ["config", "reactive"]
    await root.plugin(watcher)
    await settle()

    with root.config.override({"http": {"timeout": 1}}):
        pass
    assert seen == [30, 1, 30]

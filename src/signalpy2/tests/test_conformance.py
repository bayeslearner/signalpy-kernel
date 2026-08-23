"""Conformance against Cordis's documented semantics, not against this port.

Every assertion here traces to `vendor/cordis/src/*.ts` in deepseek-harness.
This is the gate for vendoring decisions and for taking upstream changes —
a port that passes its own suite can still fail this one, and two of the three
public Python ports do.
"""

import asyncio

import pytest

from signalpy2.cordis import Context, Service


async def settle(n=10):
    """Let deferred fiber transitions (notify -> reload) finish."""
    for _ in range(n):
        await asyncio.sleep(0)


def make_db():
    class DB(Service):
        provide = "db"

        def __init__(self, ctx, config=None):
            super().__init__(ctx)
            self.tag = config.get("tag", "A") if isinstance(config, dict) else "A"

    return DB


def make_consumer(log):
    """A plugin that registers two effects and one listener, then a disposer."""

    def consumer(ctx, config=None):
        log.append(f"start:{ctx.db.tag}")

        def eff(n):
            def execute():
                log.append(f"acquire{n}")
                return lambda: log.append(f"release{n}")

            return execute

        ctx.effect(eff(1), "e1")
        ctx.effect(eff(2), "e2")
        ctx.on("ping", lambda: log.append("pong"))
        return lambda: log.append("stop")

    consumer.inject = ["db"]
    return consumer


async def test_inject_gates_activation():
    """registry.ts: a plugin only loads while every injected service exists."""
    log = []
    root = Context()
    await root.plugin(make_consumer(log))
    await settle()
    assert log == []


async def test_starts_when_provider_appears():
    """reflect.ts:notify -> fiber._refresh -> _reload."""
    log = []
    root = Context()
    await root.plugin(make_consumer(log))
    await root.plugin(make_db(), {"tag": "A"})
    await settle()
    assert log[:3] == ["start:A", "acquire1", "acquire2"]


async def test_listener_registered_inside_a_plugin_is_live():
    log = []
    root = Context()
    await root.plugin(make_consumer(log))
    await root.plugin(make_db(), {"tag": "A"})
    await settle()
    log.clear()
    root.emit("ping")
    assert log == ["pong"]


async def test_waterfall_listener_takes_only_event_args():
    """events.ts binds the carrier as `this`; it is never an argument.

    This is the assertion the vendored port originally failed. See VENDORED.md.
    """
    root = Context()
    root.on("gate", lambda payload, next_: next_())
    assert root.waterfall("gate", "good", lambda: "allowed") == "allowed"


async def test_waterfall_vetoes_when_next_is_not_called():
    root = Context()
    root.on("gate", lambda payload, next_: "denied" if payload == "bad" else next_())
    assert root.waterfall("gate", "bad", lambda: "allowed") == "denied"
    assert root.waterfall("gate", "good", lambda: "allowed") == "allowed"


async def test_unload_is_total():
    """fiber.ts:_unload — disposers run in reverse, and nothing survives."""
    log = []
    root = Context()
    await root.plugin(make_consumer(log))
    db = await root.plugin(make_db(), {"tag": "A"})
    await settle()
    log.clear()
    await db.dispose()
    await settle()
    assert log in (["stop", "release2", "release1"], ["release2", "release1", "stop"])
    root.emit("ping")
    assert "pong" not in log


async def test_provider_swap_reactivates_dependents():
    """fiber.ts:_refresh — the epoch is a digest of providing-fiber identity."""
    log = []
    root = Context()
    await root.plugin(make_consumer(log))
    db = await root.plugin(make_db(), {"tag": "A"})
    await settle()
    await db.dispose()
    await settle()
    log.clear()
    await root.plugin(make_db(), {"tag": "B"})
    await settle()
    assert "start:B" in log


async def test_isolate_scopes_a_service_name():
    """context.ts:isolate — a child scope resolves the name independently."""
    root = Context()
    await root.plugin(make_db(), {"tag": "ROOT"})
    child = root.isolate("db")
    await child.plugin(make_db(), {"tag": "CHILD"})
    await settle()
    assert root.db.tag == "ROOT"
    assert child.db.tag == "CHILD"


async def test_duplicate_provide_in_one_scope_raises():
    """reflect.ts:provide — `service "x" has been registered at <...>`."""
    root = Context()
    await root.plugin(make_db(), {"tag": "A"})
    await settle()
    with pytest.raises(Exception, match="registered"):
        await root.plugin(make_db(), {"tag": "B"})

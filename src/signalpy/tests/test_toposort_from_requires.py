"""Toposort uses @requires contracts — the single source of truth.

`lifecycle_manager.resolve_all()` walks `meta.requirements` and adds an
edge from each provider to each consumer for every scalar non-aggregate
non-optional contract. There is no separate ordering hook: if you need
ordering you need a contract.

Aggregate (`list[X]`) and optional requirements deliberately do NOT
add edges — both are reactive paths that boot empty / None and get
filled in by the registry's change listener as providers come online.
"""
import pytest

from signalpy.kernel import (
    Kernel, component, provides, requires, lifecycle,
)


# ── Fixtures ─────────────────────────────────────────────────────────


@component("contract-provider", version="1.0")
@provides("IThing")
class ContractProvider:
    @lifecycle.activate
    def activate(self):
        self.activated = True


@component("contract-consumer", version="1.0")
@requires(thing="IThing")
class ContractConsumer:
    """Activates AFTER ContractProvider via @requires alone."""
    @lifecycle.activate
    def activate(self):
        # If toposort were broken, self.rt.thing wouldn't exist yet.
        assert self.rt.thing is not None


# ── Tests ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_requires_drives_toposort():
    """A consumer with @requires(X) activates after the X provider."""
    kernel = Kernel()
    kernel.discover([ContractConsumer, ContractProvider])  # reverse order
    await kernel.boot()

    boot = [b["name"] for b in kernel.boot_order()]
    assert boot.index("contract-provider") < boot.index("contract-consumer"), (
        f"Provider must boot before consumer; got: {boot}"
    )

    consumer_ci = kernel.lifecycle.get_instance("contract-consumer")
    assert consumer_ci.instance.rt.thing is not None
    await kernel.shutdown()


@pytest.mark.asyncio
async def test_aggregate_requires_does_not_block_boot():
    """list[X] aggregate @requires must NOT add a toposort edge — the
    consumer boots empty and the registry listener fills the list as
    providers come online."""
    from typing import Protocol, runtime_checkable

    @runtime_checkable
    class IPlugin(Protocol): ...

    @component("agg-host")
    @requires(plugins=list[IPlugin])
    class AggHost:
        @lifecycle.activate
        def activate(self):
            # boot proceeds even if no plugins yet — list[]
            assert isinstance(self.rt.plugins, list)

    @component("plug-a")
    @provides(IPlugin)
    class PlugA: ...

    kernel = Kernel()
    kernel.discover([AggHost, PlugA])
    await kernel.boot()
    # Both activated; relative order doesn't matter for aggregate
    boot = [b["name"] for b in kernel.boot_order()]
    assert "agg-host" in boot
    assert "plug-a" in boot
    await kernel.shutdown()


@pytest.mark.asyncio
async def test_optional_requires_does_not_block_boot():
    """`optional=True` @requires must not add a toposort edge — the
    consumer boots even if no provider exists."""
    @component("optional-consumer")
    @requires(thing="IUnseen", optional=True)
    class OptConsumer:
        @lifecycle.activate
        def activate(self):
            assert self.rt.thing is None

    kernel = Kernel()
    kernel.discover([OptConsumer])
    await kernel.boot()
    boot = [b["name"] for b in kernel.boot_order()]
    assert "optional-consumer" in boot
    await kernel.shutdown()

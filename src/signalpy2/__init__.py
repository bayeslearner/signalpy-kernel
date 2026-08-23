"""SignalPy 2 — a Cordis-shaped plugin kernel for Python.

1.0 (`signalpy`) is declarative: a class carries decorator metadata, the kernel
reads it up front and wires everything, teardown happens per component.

2.0 is imperative, because that is what makes a plugin architecture work: a
plugin is a callable that registers things and every registration hands back its
undo. The fiber owns the undos, so unload is total, so hot reload falls out for
free rather than being a feature. This is Cordis's model, and it is the model
DeepSeek Harness is built on — which means dsh's subsystem docs, its 58 service
keys and its five-stage tool pipeline stay a readable specification for anything
built here.

What 2.0 keeps from 1.0 is what Cordis does not have: the reactive engine
(`Signal`/`Computed`/`Effect`) and supervision trees.

    from signalpy2 import Context, Service

    class Greeter(Service):
        provide = "greeter"
        def hello(self, name):
            return f"hello {name}"

    def app(ctx, config=None):
        ctx.on("ready", lambda: print(ctx.greeter.hello("world")))
    app.inject = ["greeter"]

    async def main():
        root = Context()
        await root.plugin(Greeter)
        await root.plugin(app)
        root.emit("ready")

See `VENDORED.md` for where the kernel came from and what was changed in it.
"""

from .cordis import (  # noqa: F401
    Context,
    CordisError,
    DisposableList,
    Fiber,
    FiberState,
    Impl,
    Inject,
    Loader,
    Logger,
    LoggerService,
    ReflectService,
    RegistryService,
    Service,
    ValidationError,
)
from .cordis.events import AggregateError, EventsService, is_bailed  # noqa: F401
from .cordis.utils import this_  # noqa: F401
from .binding import bind, provide, snake_case  # noqa: F401
from .signals import Computed, Effect, Signal, batch, is_stale  # noqa: F401

# The shipped services. They have no privileged status — each is an ordinary
# plugin you mount or don't, re-exported here only for convenience.
from .services.config import ConfigService  # noqa: F401
from .services.reactive import ReactiveService  # noqa: F401
from .services.supervision import Policy, SupervisorService  # noqa: F401
from .services.tools import (  # noqa: F401
    Accept,
    Allow,
    Ask,
    Block,
    Deny,
    Tool,
    ToolExecution,
    ToolResult,
    ToolsService,
    timeout_policy,
)

__all__ = [
    # kernel
    "Context",
    "Service",
    "Fiber",
    "FiberState",
    "Inject",
    "Impl",
    # services mixed onto every context
    "EventsService",
    "ReflectService",
    "RegistryService",
    "LoggerService",
    "Logger",
    # composition
    "Loader",
    # bindings — plain classes become services without importing the kernel
    "provide",
    "bind",
    "snake_case",
    # signals — a standalone library, no kernel involved
    "Signal",
    "Computed",
    "Effect",
    "batch",
    "is_stale",
    # shipped services — ordinary plugins, mount what you need
    "ReactiveService",
    "SupervisorService",
    "Policy",
    "ConfigService",
    "ToolsService",
    "Tool",
    "ToolExecution",
    "ToolResult",
    "Allow",
    "Deny",
    "Ask",
    "Accept",
    "Block",
    "timeout_policy",
    # dispatch
    "this_",
    "is_bailed",
    # errors
    "CordisError",
    "ValidationError",
    "AggregateError",
    # utilities
    "DisposableList",
]

__version__ = "2.0.0.dev0"

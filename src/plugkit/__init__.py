"""plugkit — a plugin kernel for Python.

**Every registration returns its undo, and something owns it.**

A component adds a route to a shared server, then unloads. The route stays,
because nothing recorded who added it. That is not a missing feature, it is a
missing invariant. Here the fiber — the object representing a plugin's lifetime —
holds every disposer that plugin produced, and calls them on unload. Hot reload,
dependency-driven activation, and safe implementation swapping are consequences
of that rather than separate features.

Your components stay plain objects. The class below imports nothing from here:

    # services/greeter.py
    class Greeter:
        def __init__(self, database, prefix="hello"):
            self.database = database
            self.prefix = prefix

        def hello(self, name):
            return f"{self.prefix} {name}"

    # app.py — the only file that knows a kernel exists
    from plugkit import Context, provide

    async def main():
        root = Context()
        await root.plugin(provide(Database, "database"))
        await root.plugin(provide(Greeter, "greeter", needs=["database"]))
        print(root.greeter.hello("world"))

`Service` (exported below) is for plugins that *are* kernel surface — the shipped
`ConfigService`, `ToolsService` and friends. Your own code wants `provide()`.

The kernel is a port of Cordis, the plugin framework underneath DeepSeek Harness,
so dsh's documentation stays a working specification for anything built here. See
`VENDORED.md` for which port, why, and what changed in it.

Replaces `signalpy-kernel` 0.4.0, which is retired.
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
from .binding import bind, plugin, provide, snake_case  # noqa: F401
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
    "plugin",
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

__version__ = "0.1.0"

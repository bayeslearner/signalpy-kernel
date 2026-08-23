"""`ctx.tools` — a tool registry with the five-stage execution pipeline.

This is the piece the waterfall fix in the kernel was for. dsh calls it the
widest and most useful extension surface it has, and the shape is worth copying
exactly, because it is the difference between "I can add a tool" and "I can add
a rule about everyone's tools without touching any of them".

Every call passes through five stages:

    1. tools/pre-execute    waterfall    Allow | Deny | Ask
    2. ctx.tools.guard()    monotonic    a reason string, or None
    3. tools/execute        waterfall    wraps the call — timeouts, retries, metrics
    4. tools/post-execute   waterfall    Accept | Block — change or reject the result
    5. tools/result         emit         observe only; everything is frozen

Which stage you want:

    ask a human first          stage 1   the only stage with an Ask
    a rule nobody can override stage 2   guards cannot allow, only deny
    timeout / retry / measure  stage 3   the only stage holding the whole call
    change or reject a result  stage 4   stage 5 is immutable
    log, audit, count          stage 5   doing it in 4 races other listeners

Stage 1 has no "rewrite the arguments" option, deliberately: by then the
arguments are already in the log and on screen, and letting a listener change
them would make history, audit, display and execution disagree.

Stage 2 is monotonic — a guard returns a denial reason or nothing, and there is
no allow. That is why registration order cannot turn a denial back into
permission, and it is what makes a guard a rule rather than a suggestion.

`Ask` fails closed. No approver registered, an approver that raises, or an
approver returning anything but True all become a denial.

Tools are duck-typed. Anything with `name`, `description`, `parameters` and
`execute` works, so a tool provider can stay a plain object:

    class SearchTool:                      # imports nothing from signalpy2
        name = "search"
        description = "Search the index."
        parameters = {"type": "object", "properties": {"q": {"type": "string"}}}
        def execute(self, arguments, execution):
            return self.index.query(arguments["q"])
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from ..cordis import Service

log = logging.getLogger(__name__)

__all__ = [
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
]


# ── data ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Tool:
    """A convenience shape. Any object with these attributes also works."""

    name: str
    description: str
    execute: Callable[..., Any]
    parameters: dict = field(default_factory=dict)
    destructive: bool = False
    timeout_s: float | None = None


@dataclass(frozen=True)
class ToolExecution:
    """One call, frozen. Handed to every stage."""

    name: str
    arguments: dict
    id: str
    caller: Any = None
    tool: Any = None


@dataclass
class ToolResult:
    ok: bool
    value: Any = None
    error: dict | None = None

    @staticmethod
    def failure(code: str, message: str) -> "ToolResult":
        return ToolResult(ok=False, error={"code": code, "message": message})


# ── stage decisions ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class Allow:
    pass


@dataclass(frozen=True)
class Deny:
    reason: str


@dataclass(frozen=True)
class Ask:
    reason: str | None = None


@dataclass(frozen=True)
class Accept:
    """Stage 4: keep the result, optionally replacing its value."""

    value: Any = None
    replaced: bool = False

    @staticmethod
    def replacing(value: Any) -> "Accept":
        return Accept(value=value, replaced=True)


@dataclass(frozen=True)
class Block:
    """Stage 4: reject the result and give the caller feedback instead."""

    feedback: str


async def _maybe_await(value: Any) -> Any:
    """Await if awaitable. Sync and async listeners both work in a waterfall."""
    if inspect.isawaitable(value):
        return await value
    return value


class ToolsService(Service):
    """Provides `ctx.tools`."""

    provide = "tools"

    def __init__(self, ctx, config=None):
        super().__init__(ctx)
        self._tools: dict[str, Any] = {}
        self._guards: list[Callable[[ToolExecution], str | None]] = []
        self._approver: Callable[[ToolExecution, str | None], Any] | None = None

    # ── registration ──────────────────────────────────────────────────

    def register(self, tool: Any):
        """Register a tool. Returns a disposer owned by the calling plugin.

        Raises if `name` is already taken — two tools under one name is a bug
        that would otherwise surface as the wrong one being called.
        """
        for attribute in ("name", "description", "execute"):
            if not hasattr(tool, attribute):
                raise TypeError(f"a tool needs a {attribute!r} attribute, {tool!r} has none")

        registry = self._tools
        name = tool.name

        def execute():
            if name in registry:
                raise ValueError(f"tool {name!r} is already registered")
            registry[name] = tool
            return lambda: registry.pop(name, None)

        return self.ctx.effect(execute, f"ctx.tools.register({name!r})")

    def guard(self, guard: Callable[[ToolExecution], str | None]):
        """Register a stage-2 guard. Returns a disposer.

        Return a reason string to deny, or None to leave the call alone. There
        is no allow: guards only ever reduce permission, so no later
        registration can undo yours.
        """
        guards = self._guards

        def execute():
            guards.append(guard)
            return lambda: guards.remove(guard) if guard in guards else None

        return self.ctx.effect(execute, "ctx.tools.guard()")

    def set_approver(self, approver: Callable[[ToolExecution, str | None], Any]):
        """Register who answers an `Ask`. Returns a disposer.

        Registered rather than injected so that `Ask` fails closed by default:
        a composition with no approver denies instead of hanging or allowing.
        """
        service = self

        def execute():
            previous = service._approver
            service._approver = approver

            def dispose():
                service._approver = previous

            return dispose

        return self.ctx.effect(execute, "ctx.tools.set_approver()")

    # ── inspection ────────────────────────────────────────────────────

    def get(self, name: str) -> Any | None:
        return self._tools.get(name)

    def list(self) -> list:
        return list(self._tools.values())

    def names(self) -> list[str]:
        return sorted(self._tools)

    # ── the pipeline ──────────────────────────────────────────────────

    async def execute(
        self,
        name: str,
        arguments: dict | None = None,
        *,
        caller: Any = None,
        id: str | None = None,
    ) -> ToolResult:
        """Run a tool through all five stages. Never raises."""
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult.failure("UNKNOWN_TOOL", f"no tool named {name!r}")

        execution = ToolExecution(
            name=name,
            arguments=dict(arguments or {}),
            id=id or uuid.uuid4().hex,
            caller=caller,
            tool=tool,
        )

        decision = await self._stage1(execution)
        if isinstance(decision, Deny):
            return self._denied(execution, decision.reason)

        reason = self._stage2(execution)
        if reason is not None:
            return self._denied(execution, reason)

        result = await self._stage3(execution)
        result = await self._stage4(execution, result)
        self._stage5(execution, result)
        return result

    async def _stage1(self, execution: ToolExecution):
        async def default():
            return Allow()

        decision = await _maybe_await(
            self.ctx.waterfall("tools/pre-execute", execution, default)
        )
        if isinstance(decision, Ask):
            return await self._resolve_ask(execution, decision)
        if isinstance(decision, (Allow, Deny)):
            return decision
        log.warning("tools/pre-execute returned %r, treating as deny", decision)
        return Deny("pre-execute listener returned an unrecognised decision")

    async def _resolve_ask(self, execution: ToolExecution, ask: Ask):
        if self._approver is None:
            return Deny(ask.reason or "approval required, but no approver is registered")
        try:
            answer = await _maybe_await(self._approver(execution, ask.reason))
        except Exception as exc:
            log.exception("approver raised for %s", execution.name)
            return Deny(f"approval failed: {exc}")
        if answer is True:
            return Allow()
        return Deny(ask.reason or "denied by approver")

    def _stage2(self, execution: ToolExecution) -> str | None:
        for guard in list(self._guards):
            try:
                reason = guard(execution)
            except Exception as exc:
                log.exception("guard raised for %s", execution.name)
                return f"guard failed: {exc}"
            if reason:
                return reason
        return None

    async def _stage3(self, execution: ToolExecution) -> ToolResult:
        async def default():
            body = execution.tool.execute
            try:
                value = await _maybe_await(body(execution.arguments, execution))
            except TypeError as exc:
                # a one-argument tool body is fine too
                if "positional argument" not in str(exc):
                    raise
                value = await _maybe_await(body(execution.arguments))
            return ToolResult(ok=True, value=value)

        try:
            return await _maybe_await(
                self.ctx.waterfall("tools/execute", execution, default)
            )
        except asyncio.CancelledError:
            return ToolResult.failure("ABORTED", f"{execution.name} was cancelled")
        except Exception as exc:
            log.exception("tool %s raised", execution.name)
            return ToolResult.failure("TOOL_ERROR", str(exc))

    async def _stage4(self, execution: ToolExecution, result: ToolResult) -> ToolResult:
        async def default():
            return Accept()

        try:
            decision = await _maybe_await(
                self.ctx.waterfall("tools/post-execute", execution, result, default)
            )
        except Exception:
            log.exception("tools/post-execute raised for %s", execution.name)
            return result

        if isinstance(decision, Block):
            return ToolResult.failure("BLOCKED", decision.feedback)
        if isinstance(decision, Accept) and decision.replaced:
            return ToolResult(ok=result.ok, value=decision.value, error=result.error)
        return result

    def _stage5(self, execution: ToolExecution, result: ToolResult) -> None:
        try:
            self.ctx.emit("tools/result", execution, result)
        except Exception:
            # stage 5 is observation. A listener failing here must not be able
            # to change whether the call succeeded.
            log.exception("tools/result listener failed for %s", execution.name)

    def _denied(self, execution: ToolExecution, reason: str) -> ToolResult:
        result = ToolResult.failure("DENIED", reason)
        self._stage5(execution, result)
        return result


def timeout_policy(ctx, config=None):
    """Reference stage-3 plugin: enforce each tool's own `timeout_s`.

    A timeout notifies, it does not kill — a tool that ignores cancellation will
    not stop. Registration order decides semantics when combined with a retry
    wrapper: registered outer, the whole retry operation shares one clock;
    registered inner, each attempt gets its own.
    """

    async def wrap(execution, next_):
        budget = getattr(execution.tool, "timeout_s", None)
        if not budget:
            return await _maybe_await(next_())
        try:
            return await asyncio.wait_for(
                asyncio.ensure_future(_maybe_await(next_())), timeout=budget
            )
        except asyncio.TimeoutError:
            return ToolResult.failure(
                "TOOL_TIMEOUT", f"{execution.name} exceeded {budget}s"
            )

    ctx.on("tools/execute", wrap)


timeout_policy.name = "tool-timeout-policy"
timeout_policy.inject = ["tools"]

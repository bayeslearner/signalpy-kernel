# plugkit

**The Python port of Cordis that actually works — plus a binding layer that keeps
your components plain objects.**

> Most of this is not our code. The kernel is a vendored port of
> [Cordis][cordis], the plugin framework underneath DeepSeek Harness. What we
> add is the finding that **two of the three public Python ports are broken**,
> the suite that proves it, a fix to the third, and one original layer that keeps
> your components plain classes. Full accounting under
> [Provenance](#provenance).

```bash
pip install plugkit
```

```python
import asyncio
from plugkit import Context, provide

# Your component. A plain class. It imports nothing from plugkit.
class Greeter:
    def __init__(self, database, prefix="hello"):
        self.database = database
        self.prefix = prefix

    def hello(self, name):
        return f"{self.prefix} {name}"


class Database:
    def __init__(self, dsn="sqlite://"):
        self.dsn = dsn

    def close(self):
        print("database closed")


async def main():
    root = Context()
    await root.plugin(provide(Database, "database"))
    await root.plugin(provide(Greeter, "greeter", needs=["database"]))

    print(root.greeter.hello("world"))     # hello world

asyncio.run(main())
```

## The one idea

Here is a bug that is not a bug. A component adds a route to a shared server:

```python
def admin_api(ctx, config=None):
    ctx.server.add_route("/admin", handle)
```

Unload it. The route stays — nothing recorded who added it. The component can
remove it by hand, and will get that right today and wrong in six months when a
second route is added and only one list gets updated.

That is not a missing feature, it is a missing invariant. So plugkit has one:

```python
def admin_api(ctx, config=None):
    return ctx.server.add_route("/admin", handle)     # returns its undo
admin_api.inject = ["server"]
```

The **fiber** — the object representing this plugin's lifetime — holds that undo
and calls it on unload. You do not write teardown, cannot forget it, and cannot
get it half-right.

Everything else falls out:

- **Hot reload is free.** Reload is unload-then-apply. Unload is total, so reload is clean.
- **Dependency-driven activation is free.** A plugin that can be stopped and started cleanly can be stopped when its database leaves and started when one appears.
- **Swapping an implementation is free.** Replace a service and every plugin holding the old one is *rebuilt*, not patched — so nobody keeps a stale reference.

## Four concepts

| | |
|---|---|
| **Context** (`ctx`) | a lookup table of services, plus a scope. `ctx.database` and `ctx["database"]` are the same lookup — services are found **by name, never by type** |
| **Service** | something registered under a name — `ctx.tools`, `ctx.config` |
| **Plugin** | a callable that gets a context and registers things |
| **Fiber** | one mounted plugin and everything it registered — the unit of lifetime |

## Your components stay plain objects

The most common complaint about DI frameworks is that adopting one means
decorating your classes until they are no longer yours. `provide()` splits the
component from its registration:

```python
# services/greeter.py — no framework import, no decorator, no base class
class Greeter:
    def __init__(self, database, prefix="hello"): ...
```

```python
# app.py — the only file that knows a kernel exists
greeter = provide(Greeter, "greeter", needs=["database"], config={"prefix": "greeter.prefix"})
```

`Greeter(database=FakeDB(), prefix="hi")` works in a test with no kernel, no
container, no fixtures. Declare dependencies as a Protocol and one declaration
drives both the runtime wiring and your type checker:

```python
class GreeterDeps(Protocol):
    database: Database
    cache: Cache

provide(Greeter, "greeter", needs=GreeterDeps)     # inject == ["cache", "database"]
```

## What ships, and what is optional

The kernel is the plugin machinery. Everything else is an ordinary plugin you
mount or don't — there is no privileged "platform" tier.

| | |
|---|---|
| `plugkit.cordis` | the kernel: context, fiber, effects, five dispatch modes, registry, loader, HMR |
| `plugkit.binding` | `provide()` / `@plugin` — the wiring layer |
| `plugkit.signals` | `Signal` / `Computed` / `Effect` — a standalone library, imports nothing |
| `services.reactive` | `ctx.reactive` — signals bound to fiber lifetime |
| `services.config` | `ctx.config` — YAML/dict/env/pydantic loading, one Signal per key |
| `services.tools` | `ctx.tools` — a tool registry with a five-stage permission pipeline |
| `services.supervision` | `ctx.supervisor` — OTP-style restart strategies |

```bash
pip install "plugkit[config]"    # dependency-injector, for env/pydantic config
pip install "plugkit[hmr]"       # watchdog, for hot module replacement
```

Both degrade rather than fail: without `config`, `ConfigService` still loads
dicts and YAML.

## Why matching Cordis matters

[DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) is ~457,000
lines of TypeScript, every part of it a Cordis plugin. Because plugkit keeps
Cordis's semantics — the same event names, the same dispatch modes, the same
lifetime rules — **dsh's documentation stays a working specification for anything
you build here.** Its 58-service catalogue, its five-stage tool pipeline, its
filesystem policy events all describe a substrate that means the same thing in
this kernel.

That is the practical argument for a faithful port over a Pythonic reinterpretation,
and it is why the conformance suite tests against the TypeScript rather than
against ourselves.

## Provenance

Most of this is not original work, and the split is worth stating plainly:
**9,884 lines vendored, 3,509 written here.**

| | |
|---|---|
| **Vendored** | The kernel — a Python port of [Cordis][cordis] by [geohotstan](https://github.com/geohotstan/cordis-py), MIT. 4,298 lines of source and 5,586 of tests. We did not design it and did not write it. |
| **A finding** | Three MIT Python ports of Cordis exist. **Two are broken.** In one, `ctx.effect()` — the central API — raises `'Symbol' object is not callable`, and its own 59 tests never touch it. Another redesigned the API around typed tokens, which forfeits the reason to port Cordis at all. We could not find anyone who had published this. |
| **The suite that proves it** | `test_conformance.py` — nine assertions traced to `vendor/cordis/src/*.ts` rather than to any implementation. It scored the three ports 6/9, 5/9 and n/a, and it is the gate for taking any upstream change. |
| **A fix** | The surviving port passed the dispatch carrier as a leading positional argument to every listener, where Cordis binds it as `this`. That silently changes the arity of every listener, so any plugin written from dsh's documentation breaks. Now ambient, via a `ContextVar`. |
| **One original layer** | `binding.py` — 346 lines letting your components stay plain classes with no framework import. The genuinely new part, and the reason to take this over writing your own port. |
| **A tool pipeline** | `services/tools.py` — our code, DeepSeek's design, ported stage for stage. |
| **Carried forward** | `signals.py` and the supervision strategies come from `signalpy-kernel`, this project's retired predecessor. |

**Why vendor rather than depend?** The port we started from is pre-1.0, has no
PyPI release, and one author. That is a fork, not a dependency, and pretending
otherwise would put your build on someone's weekend project.
`src/plugkit/VENDORED.md` lists every change made to it.

[cordis]: https://github.com/deepseek-ai/deepseek-harness/tree/master/vendor/cordis

## Development

```bash
uv run pytest src/plugkit/tests -q          # 235 passed, 3 skipped, 2 xfailed
uv run --with pyright pytest src/plugkit/tests/test_typing.py   # typing checks
```

- Architecture: [`docs/design/kernel-architecture.md`](docs/design/kernel-architecture.md)
- What the project lives or dies on: [`docs/steering/pillars.md`](docs/steering/pillars.md)
- Current sprint: the head of [`specs/`](specs/)

## Replaces signalpy-kernel

`signalpy-kernel` 0.4.0 was the previous design: a reactive component microkernel
with twelve decorators. It remains on PyPI and is not going anywhere, but it is
retired and receives no further work. plugkit is not a version of it — it is a
different design of the same thing, and nothing carries over unchanged except the
Signals library and the supervision strategies.

The reason for the break: 1.0's components had to import the kernel, and nothing
in it owned the undo of what a component registered. Those are the two things
plugkit exists to fix. `specs/03-plugkit-kernel/spec.md` records the decisions;
`docs/history/2026-08-v1-book/` preserves 1.0's documentation.

MIT.

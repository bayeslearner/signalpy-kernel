# SignalPy 2 — a Cordis-shaped plugin kernel for Python

> Status: the kernel and the three grafts are in and tested (182 passing).
> Nothing depends on this yet. 1.0 (`src/signalpy`) is untouched and still
> vendored in prismi3.

## Why 2.0 is not 1.0 with more features

1.0 is **declarative**. A class carries decorator metadata — `@component`,
`@provides`, `@requires`, `@runnable`, `@subscribe`, `@kind`, `@skill`, `@prop`,
`@api` — the kernel reads it up front, wires everything, and tears down per
component.

That model cannot express a plugin system. Nothing owns the undo of what a
plugin registered, so unload is never total, so hot reload has to be built
rather than inherited. And twelve vocabulary items is a lot to hold for what is
mechanically "a thing that declares what it needs and offers".

2.0 is **imperative**, which is Cordis's model and therefore DeepSeek Harness's:

```python
from signalpy2 import Context, Service

class Greeter(Service):
    provide = "greeter"
    def hello(self, name):
        return f"hello {name}"

def app(ctx, config=None):
    ctx.on("ready", lambda: print(ctx.greeter.hello("world")))
    handle = open_something()
    return handle.close          # ← the plugin's undo

app.inject = ["greeter"]         # ← does not run until `greeter` exists

async def main():
    root = Context()
    await root.plugin(Greeter)
    await root.plugin(app)
    root.emit("ready")
```

Four concepts instead of twelve: **plugin**, **context**, **service**, **effect**.
Every registration returns its disposer, the fiber owns the disposers, so unload
is total and hot reload falls out of that rather than being a feature.

Choosing Cordis's semantics has a second payoff: **dsh's documentation stays a
valid specification.** Its 58 service keys, its five-stage `tools/*` pipeline,
its `fs/*` policy events, `docs/subsystems/*` and `docs/capability-seams.md` all
describe a substrate that means the same thing here.

## What's in it

| | from | what |
|---|---|---|
| kernel | vendored Cordis port, fixed — see `VENDORED.md` | context, service, fiber, effects, 5 dispatch modes, registry, loader, HMR |
| `ReactiveService` | 1.0 | `Signal` / `Computed` / `Effect`, fiber-owned |
| `SupervisorService` | 1.0 | restart strategies on Cordis's unused `FAILED` state |
| `ConfigService` | `dependency-injector` | YAML/dict/env/pydantic loading, per-key reactive reads |

Everything above the kernel is a plugin. Mount what you need.

### Reactive, because epoch reload is the wrong granularity for a value

Cordis reloads a whole plugin when a *provider* changes identity. Right for "the
database service was replaced", wrong for "a timeout changed". So Signals:

```python
def http(ctx, config=None):
    ctx.reactive.effect(lambda: ctx.client.set_timeout(ctx.config.get("http.timeout", 30)))
http.inject = ["config", "reactive", "client"]
```

The effect is registered against `http`'s fiber, so it is disposed when `http`
unloads. No teardown written by hand. A `ctx.config.set("http.timeout", 60)`
re-runs that effect and nothing else — config keys get one Signal each.

### Supervision, because Cordis sets FAILED and walks away

```python
db = await root.plugin(Database)
root.supervisor.supervise(db, strategy="one_for_all", max_restarts=5, within=60)
```

`one_for_one` / `one_for_all` / `rest_for_one`, constant/linear/exponential
backoff. Exceeding the budget emits `supervisor/escalate` and stops.

### Config, because this is the one place an existing library wins

`dependency-injector`'s `providers.Configuration` is a mature loader — YAML,
dicts, env with defaults, Pydantic settings, `.override()` for tests. It is
pull-based and cannot tell anyone a value changed, so loading comes from it and
propagation comes from a Signal. The dependency is optional; without it the
service still works from dicts and YAML.

## What did not come across from 1.0, and why

- **`traits.py`** (L0–L3) — auto-derived labels that nothing consumed for
  behaviour. `kernel.status()` printed them. Inspection dressed as architecture.
- **`@kind`, `@skill`** — prismi3 domain concepts in a general kernel, against
  1.0's own constitution rule 3.
- **`@prop`, `@api`** — metadata for one or two call sites.
- **`@runnable` + `HandlerSchema` + transports** — the most useful thing in 1.0
  and the least kernel-ish. It is a tool/RPC layer. It belongs here as a
  `ctx.tools` plugin, which is what dsh calls it too. Not ported yet.
- **`@requires` map-mode** (inject services keyed by a property) — iPOPO
  inheritance, used approximately once.

## Running

```bash
uv run pytest src/signalpy2/tests -q
```

`test_conformance.py` is the gate that matters: nine assertions traced to
`vendor/cordis/src/*.ts` rather than to this implementation. It is what decided
which of the three public Cordis ports to vendor, and it is what should be run
first when taking any upstream change.

## Not done

- `ctx.tools` — the tool registry and its five-stage pipeline (`tools/pre-execute`
  et al). This is the next piece, and the reason the waterfall fix mattered.
- Typed `ctx` — TS declaration merging has no Python equivalent, so `ctx.tools`
  is `Any`. Mitigate with `Protocol` stubs and a generated `.pyi`, or accept it.
- A migration path for 1.0 components. The decorator surface could be kept as a
  veneer over `ctx.plugin()` so prismi3's `src/backend` moves incrementally
  rather than at once.

# plugkit

**plugkit builds a Python application out of parts that can be added and removed
while the program is running.**

You write ordinary classes. plugkit constructs them in dependency order, passes
each one what it asked for, and makes them reachable by name. When a part is
removed, everything that part registered is removed with it.

## What it provides

| | |
|---|---|
| **Dependency injection** | Declare what a class needs. plugkit constructs it and passes in the dependencies. Your classes need no decorators, no base class, and no import from plugkit. |
| **Startup without a boot sequence** | A part runs once its dependencies exist, not at a position you chose. The order you register parts in does not matter. |
| **Guaranteed teardown** | Each part returns a function that undoes its work. plugkit calls it whenever the part is removed, for any reason. |
| **Add and remove at runtime** | Load and unload parts while the program runs, including reloading source files you have just edited. |
| **Implementation swapping** | Replace one service with another. Every part that used the old one is rebuilt with the new one, so none keeps a stale reference. |
| **Composition from a file** | Describe an application as a YAML list of parts and their settings. |

Four services ship alongside, each an ordinary part you mount or leave out:
configuration, reactive values, supervised restarts, and a tool registry with a
permission pipeline.

## Why this is not already in Python

Python has three of the four pieces.

| Piece | Provided by |
|---|---|
| **Discovery** — find installed plugins | entry points (`importlib.metadata`), `stevedore` |
| **Dispatch** — call into plugin code | `pluggy`, the plugin system behind pytest |
| **Construction** — build objects and pass in dependencies | `injector`, `dependency-injector`, `lagom`, `svcs` |
| **Lifetime ownership** — undo everything a plugin did | mostly absent |

The fourth is the gap. `pluggy` can unregister a plugin's hooks, and
`dependency-injector`'s `Resource` provider can shut down one object it built.
Neither tracks what the plugin *did*: the route it added to a shared server, the
listener it attached, the connection it opened, the background task it started.

Running the pluggy case makes the boundary concrete:

```python
pm.register(MyPlugin(), name="mine")
pm.hook.startup()                        # the plugin writes shared_routes["/admin"]

pm.unregister(name="mine")
pm.get_plugin("mine")                    # None  — the hooks are gone
shared_routes                            # {'/admin': 'handler'}  — the effect is not
```

That is not a defect in pluggy. Dispatching hooks is what pluggy is for. But it
means cleanup is a method you write and remember to call, and no framework can
check that you wrote it correctly.

Two reasons the gap persisted. Python's deployment model is restart-oriented: you
edit a file and restart the process, so few libraries needed to remove a
component from a live program. And `import` is permanent — `sys.modules` caches
modules and the language has no unload — so ecosystems built around load-once
rather than solving retraction. [`iPOPO`](https://ipopo.readthedocs.io), a port
of OSGi, is the main exception.

Searching for prior art in August 2026 returned Cordis ports and nothing else
that owns a component's side effects. `stevedore`'s own documentation describes
itself as building on entry points to avoid "creating yet another extension
mechanism", which is discovery, not lifetime.

## Why one rule is enough to build on

The rule is that a registration returns its undo, and the fiber owns the undo.
Three capabilities are consequences of it rather than separate features:

| Capability | Derivation |
|---|---|
| Hot reload | unload, then apply. Unload removes everything, so there is no reload machinery to write. |
| Dependency-driven activation | start when a dependency appears, stop when it leaves. Requires only that a part can be stopped cleanly. |
| Implementation swapping | unload the dependents, apply them against the new object. |

The same rule holds at scale. DeepSeek Harness is roughly 457,000 lines of
TypeScript across about 219 packages, all built on Cordis, the framework plugkit
ports. Every capability there is a plugin: the model adapter, the conversation
log, the permission system, the sandbox, and the main agent loop. Replacing the
agent loop means mounting a different plugin, not editing the framework.

## When to use it

Use plugkit when parts of your program need to appear and disappear while it
runs: plugin hosts, extension systems, long-running agents, servers whose
features differ per deployment, or anything that must reload without a restart.

Do not use it for a script, or for a program whose set of components is fixed at
startup. Constructing your objects directly is simpler and none of the above
applies.

> The kernel is not original work. It is a vendored port of an existing plugin
> framework, described in [Provenance](#provenance).

```bash
pip install plugkit
```

## Quick start

The program registers a greeter that needs a database before any database exists,
then supplies one, then takes it away again.

```python
import asyncio
from plugkit import Context, provide


class Database:
    def __init__(self, dsn="sqlite://"):
        self.dsn = dsn


class Greeter:
    def __init__(self, database):
        self.database = database

    def hello(self, name):
        return f"hello {name}, via {self.database.dsn}"


async def main():
    root = Context()

    # Register the greeter first. It needs a database, and none exists yet.
    greeter = await root.plugin(provide(Greeter, "greeter", needs=["database"]))
    print("greeter" in root)                 # False — it is waiting

    # The database arrives, which unblocks the greeter.
    database = await root.plugin(provide(Database, "database"))
    await greeter                            # wait for the greeter to finish loading
    print(root.greeter.hello("world"))       # hello world, via sqlite://

    # Take the database away.
    await database.dispose()
    print("greeter" in root)                 # False — it stopped with its dependency

asyncio.run(main())
```

Three things happened that nobody wrote code for. The greeter waited instead of
failing. It was constructed once its dependency existed. It stopped when that
dependency was removed.

### What `await root.plugin(...)` waits for

It waits for **that plugin's own load to finish**, and nothing else.

`root.plugin(p)` returns a fiber, which is awaitable. Awaiting it suspends until
`p`'s load transition settles, and re-raises if `p`'s function raised.

| Situation | What the await does |
|---|---|
| `p`'s function runs for 200ms | blocks for 200ms |
| `p`'s dependencies are missing | returns immediately. `p` never ran, so there is no load to wait for. The fiber is `PENDING` |
| `p` unblocks some other plugin `q` | returns when `p` is loaded. `q` is still `LOADING` at that moment |

The third row is why the example writes `await greeter` after mounting the
database. Mounting the database returns as soon as the *database* is active; the
greeter's reload is scheduled separately and has not run yet. Awaiting the
greeter's own fiber waits for it.

```python
database = await root.plugin(provide(Database, "database"))
root.greeter                # AttributeError — greeter is still LOADING
await greeter
root.greeter                # the Greeter instance
```

`await fiber.dispose()` has no such gap. It waits for the unload to complete,
including the unload it cascades to dependents, which is why the last line of the
example needs nothing after it.

## Should you use a DI container instead?

For a fixed object graph, yes. `dependency-injector` does the same wiring in
fewer lines, synchronously, with no strings:

```python
class Container(containers.DeclarativeContainer):
    database = providers.Singleton(Database)
    greeter  = providers.Singleton(Greeter, database=database)

Container().greeter().hello("world")     # hello world
```

plugkit costs more to write. It is worth that cost only when components appear
and disappear while the program runs. Measured against
`dependency-injector` 4.x:

| | `dependency-injector` | plugkit |
|---|---|---|
| Wire a fixed graph | 2 lines, synchronous | 2 lines, `async` |
| Request a service that does not exist | `AttributeError` | the dependent waits in `PENDING` until it appears |
| Swap an implementation | the existing dependent keeps the old object until you call `full_reset()` | dependents are rebuilt automatically; the replaced objects' `close()` runs |
| Remove a service | no API for it | dependents stop, their `close()` runs, the name disappears |
| Undo what a component registered elsewhere | not tracked | the fiber owns it |

Choose a container when the answer to "what runs in this process" is decided at
startup. Choose plugkit when it is not.

## Four terms

| Term | Definition |
|---|---|
| **Context** (`ctx`) | A table mapping names to objects. `ctx.database` and `ctx["database"]` both look up the name `"database"`. |
| **Service** | An object registered in a context under a name. |
| **Plugin** | A function `(ctx, config)` that registers things. |
| **Fiber** | One mounted plugin, plus everything it registered. The unit of lifetime. |

Services are found by **name**, never by type. `needs=["database"]` means "the
service registered under the string `database`". The class is never inspected.

## Why a plugin returns a disposer

This example has two plugins. The first owns a `Server` object. The second adds
a route to it. When the second plugin is unloaded its route stays behind, and the
rest of this section fixes that.

`Server` is your class. The kernel has no knowledge of its contents.

```python
class Server:
    def __init__(self):
        self.routes = {}
    def add_route(self, path, handler):
        self.routes[path] = handler
    def remove_route(self, path):
        self.routes.pop(path, None)
```

Register one instance under the name `"server"`:

```python
await root.plugin(provide(Server, "server"))
```

`ctx.server` returns that instance. `type(ctx.server)` is `Server`.
`ctx.server.add_route(...)` is a normal method call.

A second plugin adds a route:

```python
def admin_api(ctx, config=None):
    ctx.server.add_route("/admin", lambda: "admin page")

admin_api.inject = ["server"]
```

Unload it:

```python
await fiber.dispose()
print(list(root.server.routes))     # ['/admin']
```

The route remains. The kernel did not remove it, because the kernel never
recorded it. `routes` is your dict and `add_route` is your method. The kernel
recorded one fact: an object is registered under `"server"`, and `admin_api`
requires it.

Return a function that reverses the change:

```python
def admin_api(ctx, config=None):
    ctx.server.add_route("/admin", lambda: "admin page")
    return lambda: ctx.server.remove_route("/admin")

admin_api.inject = ["server"]
```

Mounting and then disposing the plugin now prints:

```
['/admin']
[]
```

You write that lambda. `add_route` returns `None`, and no kernel can change what
your methods return. The kernel stores your lambda on the fiber and calls it on
every unload path:

- the `server` service is replaced by another implementation
- a config value the plugin was built from changes
- a supervisor restarts the plugin after a failure
- the application shuts down
- the module is edited and hot-reloaded

To reverse more than one change, use `ctx.effect`. It stores each disposer and
starts them all on unload, in reverse registration order.

```python
def admin_api(ctx, config=None):
    def route(path, handler):
        def install():
            ctx.server.add_route(path, handler)
            return lambda: ctx.server.remove_route(path)
        return install

    ctx.effect(route("/admin", admin_page))
    ctx.effect(route("/health", health_check))
```

Three properties follow from total unload:

- **Hot reload.** Reload is unload followed by apply. Unload removes everything,
  so reload starts clean. There is no separate reload mechanism.
- **Dependency-driven activation.** A plugin that stops and starts cleanly can be
  stopped when its database disappears and started when one appears.
- **Implementation swapping.** Replace a service and every plugin holding the old
  object is rebuilt rather than patched, so no plugin keeps a stale reference.

## Writing a plugin

A plugin function takes **exactly two parameters**.

```python
def my_plugin(ctx, config=None):
    ...
```

One parameter or three raises `TypeError` and the fiber enters the `FAILED`
state. Write `config=None` if you do not use it.

### The two kinds of config

`config` (the parameter) and `ctx.config` (a service) are unrelated.

| | `config` parameter | `ctx.config` |
|---|---|---|
| What it is | this mount's own settings | a shared settings service |
| Where it comes from | the second argument to `ctx.plugin(plugin, config)` | `ConfigService`, an ordinary plugin |
| How many exist | one per mount | one per application |
| Requires `inject` | no | yes — `inject = ["config"]` |
| Present without `ConfigService` | yes | no |

The parameter cannot be replaced by the service, because a plugin can be mounted
more than once at the same time:

```python
await root.plugin(server, {"port": 8080})
await root.plugin(server, {"port": 9090})
# the function runs twice, receiving {"port": 8080} and {"port": 9090}
```

A single shared `ctx.config` cannot express two different ports for two live
instances of the same plugin. The per-mount config also drives reload:
`fiber.update(new_config)` unloads the plugin and applies it again with the new
value.

Use `ctx.config` for application-wide settings such as a log level or a database
URL. Use the parameter for what distinguishes one mount from another.

### `inject`

Every plugin that uses a service must declare it. The declaration is a list of
names on the function:

```python
admin_api.inject = ["server"]
```

`inject` lists the service names this plugin requires. It does three things:

1. **Gates activation.** The function does not run until every listed name is
   registered. Until then the fiber stays in the `PENDING` state.
2. **Grants access.** Reading a service that is not in `inject` raises
   `AttributeError`. `inject` is also the permission list.
3. **Ties lifetime.** If a listed service is removed, the plugin unloads.

Point 2 exists because of point 3. The kernel decides when to reload a plugin by
tracking the identity of the fibers providing its injected services. A dependency
the kernel cannot see is one whose replacement will not trigger a reload, leaving
the plugin holding a stale object.

`@plugin` is an alternative to attribute assignment. Assigning `fn.inject` runs
correctly but fails type checking, because pyright rejects arbitrary attributes
on a function.

```python
from plugkit import plugin

@plugin(inject=["server"])
def admin_api(ctx, config=None):
    ...
```

With no explicit `inject`, `@plugin` reads the list from a Protocol annotating
the first parameter. See [Typed contexts](#typed-contexts).

## Components stay plain objects

`provide()` separates a component from its registration. The component is a class
with a normal constructor and no framework markup.

```python
# services/greeter.py — imports nothing from plugkit
class Greeter:
    def __init__(self, database, prefix="hello"):
        self.database = database
        self.prefix = prefix
```

The wiring lives in a separate file:

```python
# app.py — the only file that imports plugkit
from plugkit import provide
from services.greeter import Greeter

greeter = provide(Greeter, "greeter", needs=["database"],
                  config={"prefix": "greeter.prefix"})
```

`Greeter(database=FakeDB(), prefix="hi")` works in a test with no kernel and no
fixtures.

### Arguments to `provide()`

| Argument | Meaning |
|---|---|
| `factory` | the class or callable to construct |
| `service_name` | the name to register the result under. Required. |
| `needs` | services to pass to the constructor |
| `config` | constructor arguments read from `ctx.config` |
| `close` | teardown method name, or `False`. Auto-detected otherwise. |
| `extra` | literal constructor arguments |

`service_name` is required because the name is the component's public interface.
An earlier version defaulted it to `snake_case(factory.__name__)`. Renaming
`Database` to `PostgresDatabase` then changed the service name to
`postgres_database`, and every dependent stopped activating with no error,
because a plugin waiting for an absent service is indistinguishable from one
whose turn has not come.

Naming the service yourself also separates the role from the implementation:

```python
provide(PostgresDatabase, "database")     # today
provide(SqliteDatabase,   "database")     # tomorrow, no dependent changes
```

### Declaring dependencies

Three forms:

```python
needs=["database"]              # constructor kwarg and service share a name
needs={"db": "database"}        # kwarg `db` receives service `database`
needs=GreeterDeps               # a Protocol
```

The Protocol form removes a duplication:

```python
from typing import Protocol

class GreeterDeps(Protocol):
    database: Database
    cache: Cache

provide(Greeter, "greeter", needs=GreeterDeps)     # inject == ["cache", "database"]
```

`typing.get_protocol_members` (Python 3.13+) reads the member names off the
Protocol at runtime. The same declaration produces the injection list and type
checks the constructor.

### Config reaching the constructor

A constructor argument can come from `ctx.config` instead of from a service. Give
`config` a mapping of constructor keyword to `(key, default)`:

```python
provide(Database, "database", config={"dsn": ("db.dsn", "sqlite://")})
```

This reads `ctx.config.get("db.dsn", "sqlite://")` and passes it as `dsn=`.

If `ReactiveService` is mounted, changing that key rebuilds the component: the old
object's `close()` runs and a new one is constructed. A constructor argument
cannot be changed after construction, so a new object is the only correct
response. Without `ReactiveService` the binding still works and does not rebuild.

## Typed contexts

`Context.__getattr__` returns `Any`, because which services exist depends on which
plugins are mounted. Annotate your own parameter instead.

```python
from typing import Any, Protocol
from plugkit import plugin

class Tools(Protocol):
    def register(self, tool: Any) -> Any: ...

class ReportDeps(Protocol):
    database: Database
    tools: Tools
    def on(self, event: str, listener: Any) -> Any: ...

@plugin
def report(ctx: ReportDeps, config=None) -> None:
    rows = ctx.database.query("SELECT 1")   # typed
    ctx.databse                             # pyright: Cannot access attribute
```

Checked against pyright:

| Approach | Result |
|---|---|
| pass a raw `Context` where a Protocol is expected | rejected. `__getattr__ -> Any` does not satisfy protocol members |
| annotate your own parameter with a Protocol | works. Completion and typo detection |
| `get[T](token: type[T]) -> T` token lookup | works |
| `cast(MyDeps, ctx)` at the top of the function | works |

`src/plugkit/tests/test_typing.py` runs pyright over these and fails if any stops
holding.

## What ships

The kernel provides the plugin machinery. Everything else is an ordinary plugin.
There is no privileged tier.

| Module | Provides |
|---|---|
| `plugkit.cordis` | the kernel: contexts, fibers, effects, five event dispatch modes, the registry, the YAML loader, hot module replacement |
| `plugkit.binding` | `provide()` and `@plugin` |
| `plugkit.signals` | `Signal`, `Computed`, `Effect`. A standalone library with no kernel import |
| `services.reactive` | `ctx.reactive` — signals bound to fiber lifetime |
| `services.config` | `ctx.config` — YAML, dict, env and pydantic loading |
| `services.tools` | `ctx.tools` — a tool registry with a five-stage permission pipeline |
| `services.supervision` | `ctx.supervisor` — restart strategies for failed fibers |

Two services need a third-party package. Install them as extras:

```bash
pip install "plugkit[config]"    # dependency-injector, for env and pydantic config
pip install "plugkit[hmr]"       # watchdog, for hot module replacement
```

Both extras degrade rather than fail. Without `config`, `ConfigService` still
loads dicts and YAML. The test suite runs in both configurations.

## Provenance

### What Cordis is

**[Cordis][cordis]** is a plugin framework written in TypeScript. Its model is the one
described above: a plugin is a function that registers things and returns their
undo, and a "fiber" owns those undos.

It is the foundation of **DeepSeek Harness**, DeepSeek's open-source agent
runtime — about 457,000 lines of TypeScript in which every capability, including
the model adapter and the main loop, is a Cordis plugin. Cordis is therefore a
design proven at a size worth copying rather than a fresh idea.

plugkit is a Python port of Cordis with the same event names, dispatch modes and
lifetime rules. Because the semantics match, DeepSeek Harness's documentation
describes this kernel accurately: its 58-service catalogue, its five-stage tool
pipeline and its filesystem policy events all apply here. Its test suite therefore
checks this implementation against the TypeScript source rather than against
itself.

### What is vendored and what is not

14,108 lines in `src/plugkit`, by origin:

| | lines | share |
|---|---|---|
| **Vendored** — the Cordis port and its test suite | 9,929 | 70% |
| **Carried forward** — `signals.py`, from `signalpy-kernel` | 597 | 4% |
| **Written here** | 3,582 | 25% |

The vendored kernel is 4,343 lines of source and 5,586 of tests, ported by
[geohotstan](https://github.com/geohotstan/cordis-py) under MIT. **77 of those
source lines are ours** — the carrier fix, two bugs in the traceable layer, and
subscript access. 49 lines of the upstream tests were changed, all of them the
mechanical listener-signature update. Every change is listed in
`src/plugkit/VENDORED.md`.

The 3,582 lines written here break down as:

| | lines |
|---|---|
| tests, including the conformance suite | 1,951 |
| `services/tools.py` — our code, DeepSeek's design, ported stage for stage | 419 |
| `binding.py` — `provide()` and `@plugin` | 378 |
| `services/config.py` | 248 |
| `services/supervision.py` — strategies from `signalpy-kernel` | 177 |
| `__init__.py` | 133 |
| `examples/` | 189 |
| `services/reactive.py` | 87 |

Over half is tests, and the largest implementation file re-implements a design
from elsewhere. The original design work is `binding.py`: 378 lines that keep
components free of framework imports.

What this project contributes beyond code:

| | |
|---|---|
| **Finding** | Three MIT Python ports of Cordis exist. Two do not work. In one, `ctx.effect()` raises `'Symbol' object is not callable`, and its 59 tests never call it. Another replaced the string-keyed API with typed tokens. |
| **Conformance suite** | `test_conformance.py`. Nine assertions traced to `vendor/cordis/src/*.ts`. It scored the three ports 6/9, 5/9 and not applicable, and gates every upstream change. |
| **Fix** | The vendored port passed the dispatch carrier as a leading positional argument to every listener. Cordis binds it as `this`. The difference changes every listener's arity, so plugins written from DeepSeek's documentation fail. |

The vendored port is pre-1.0, unpublished on PyPI, and has one author. It is
maintained here as a fork rather than consumed as a dependency.
`src/plugkit/VENDORED.md` lists every local change.

[cordis]: https://github.com/deepseek-ai/deepseek-harness/tree/master/vendor/cordis

## Development

Run the test suite:

```bash
uv run pytest src/plugkit/tests -q                              # 249 passed
uv run --with pyright pytest src/plugkit/tests/test_typing.py   # typing checks
```

- Architecture: [`docs/design/kernel-architecture.md`](docs/design/kernel-architecture.md)
- Project pillars: [`docs/steering/pillars.md`](docs/steering/pillars.md)
- Current sprint: the head of [`specs/`](specs/)

## Relationship to signalpy-kernel

`signalpy-kernel` 0.4.0 was a reactive component microkernel with twelve
decorators. It is retired and remains on PyPI. plugkit is a different design, not
a new version of it.

Two problems caused the replacement. Components had to import the kernel, so they
could not be tested or reused without it. And no object owned the undo of what a
component registered, so teardown was a promise each component made individually
and the framework could not verify.

`specs/03-plugkit-kernel/spec.md` records the decisions.
`docs/history/2026-08-v1-book/` holds the earlier documentation.

MIT.

# plugkit

A plugin kernel for Python. **Every registration returns its undo, and something
owns it.**

## What this is

A component adds a route to a shared server, then unloads. The route stays,
because nothing recorded who added it. That is a missing invariant, not a missing
feature — so this kernel has one: the **fiber** (the object representing a
plugin's lifetime) holds every disposer that plugin produced, and calls them on
unload.

Hot reload, dependency-driven activation, and safe implementation swapping are
consequences of that, not separate features.

Four concepts: **context** (a lookup table of services), **service** (something
registered under a name), **plugin** (a callable that gets a context and
registers things), **fiber** (one mounted plugin and everything it registered).

**The kernel is vendored, not ours.** ~74% of the lines are a port of Cordis, the
plugin framework underneath DeepSeek Harness. What is ours: the conformance suite
(which found two of the three public ports broken), the carrier fix to the third,
`binding.py` (the POPO layer — the one original design), and the tool pipeline
implementation. Do not let the docs drift into claiming more than that.

Matching Cordis's semantics is practical rather than decorative: it keeps dsh's
documentation a working specification for anything built here.

## Skills to load each session

`work-discipline` and `spec-driven-dev`. Add `deepseek-harness` when working on
anything that mirrors a dsh subsystem.

## Required reading (session start)

1. `docs/steering/pillars.md` — what this project lives or dies on
2. `docs/design/kernel-architecture.md` — the anchor every sprint conforms to
3. The head of the sprint queue in `specs/` — the lowest-numbered spec that is
   not CLOSED. That is where work is.

## Where truth lives

| kind | location |
|---|---|
| sprints | `specs/<NN-name>/spec.md` |
| pillars, long-lived intent | `docs/steering/` |
| stable cross-cutting design (the anchors) | `docs/design/` |
| the user-facing book | `docs/guide/`, `docs/index.qmd` |
| dated, time-bound records | `docs/history/` |
| what was vendored, why, and every change made to it | `src/plugkit/VENDORED.md` |

## Layout

Four levels, ordered by what may depend on what.

```
src/plugkit/
  cordis/       the kernel — nothing above it may be assumed present
  binding.py    provide() and @plugin — the kernel-aware wiring layer
  signals.py    Signal / Computed / Effect — a standalone library, imports nothing
  services/     ordinary plugins with NO privileged status:
                  config, reactive, supervision, tools
  examples/     typed_plugin.py, alternative_binding.py
  tests/        vendored suite + conformance + one file per feature
```

**There is no platform tier.** Config and logging are ordinary plugins, not
system services. The kernel's only built-in service is `ctx.logger`, and it earns
that because a fiber must be able to report its own load failure.

**Rule: nothing in `cordis/` may import from `services/`.** That direction would
make a service load-bearing, which is the tier this design deleted.

## Commands

Run the tests and add dependencies with `uv`:

```bash
uv run pytest src/plugkit/tests -q                 # the gate
uv run --with pyright pytest src/plugkit/tests/test_typing.py
uv add <pkg>                                        # never pip/poetry
```

Test config (`asyncio_mode`, `pythonpath`) is in `pyproject.toml`. Optional
extras: `config` (dependency-injector), `hmr` (watchdog). Both degrade rather
than fail — the suite passes with and without them, and that is deliberate.

## Working rules

**`test_conformance.py` is the gate that matters.** Nine assertions traced to
`vendor/cordis/src/*.ts` rather than to this implementation. Run it first when
taking any upstream change. It is what decided which of the three public Cordis
ports to vendor.

**Components stay plain objects.** A class the kernel wires must import nothing
from `plugkit` and must be constructible in a test with no fixtures.
`test_component_needs_no_kernel_at_all` is the guard. `Service` is for plugins
that *are* kernel surface — the shipped services. Application code uses
`provide()`.

**A test asserts the property a feature exists to provide**, not its API
surface. "A subscription dies with the plugin that made it" is a test; "effect()
returns an object" is not.

**Watch for the callable-attribute hazard.** Reading a service through a context
rebinds its *methods* onto the caller's view, so registrations are owned by the
caller's fiber. It must not touch data that happens to be callable — a provider,
a lambda, a partial. Got this wrong twice; the discriminator is whether the name
lives in the instance `__dict__`. See `VENDORED.md`.

**Simplicity over compatibility.** No shims, no dual paths. When behaviour
changes, replace rather than accrete.

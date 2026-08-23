# Pillars — what this project lives or dies on

The dimensions on which a *kernel* actually succeeds. Code is one of five, and
historically the least at risk here: 1.0 shipped working code with no spec, no
pillar file, and one ACTIVE sprint left open for four months. The pillars exist
to stop that recurring.

Every sprint advances at least one. A sprint that advances only **Kernel** and
leaves Teaching and Design untouched is a sprint that made the project harder to
adopt.

| Pillar | What it means here | Healthy when |
|---|---|---|
| **Kernel** | The plugin machinery itself: context, fiber, effects, events, registry, composition | A plugin loads when its dependencies appear, unloads totally when they go, and hot reload falls out of that rather than being a feature |
| **Adoptability** | Whether a stranger can put a component into this without adopting a religion | A component is a plain class. It imports nothing from the kernel, is constructible in a test with no fixtures, and works outside this framework unchanged |
| **Conformance** | Whether "we implement Cordis" is a claim or a fact | `test_conformance.py` passes, every assertion traced to `vendor/cordis/src/*.ts`. dsh's docs stay a usable specification for anything built here |
| **Teaching** | Whether the Quarto book explains the model, not just the API | A newcomer can read the guide end to end and write a correct plugin without reading kernel source. Every concept has a runnable example |
| **Packaging** | Whether it can actually be depended on | `pip install` works, extras are honest about what degrades without them, the vendored fork's provenance and patch list are current |

## Current state — 2026-08-23

| Pillar | State | Evidence |
|---|---|---|
| **Kernel** | 🟢 strong | 294 passing: the vendored suite, 13 conformance assertions, and one file per feature [src:src/plugkit/tests/] |
| **Adoptability** | 🟢 strong | `binding.provide()` keeps components POPO; `test_component_needs_no_kernel_at_all` is the guard [src:src/plugkit/tests/test_binding.py] |
| **Conformance** | 🟡 partial | 13 assertions cover the load-bearing semantics. The 58-key dsh service surface is one service in (`ctx.tools`); the rest is unbuilt [src:src/plugkit/services/tools.py] |
| **Teaching** | 🟢 strong | Eight chapters, from why it exists to testing, every example executed by `test_guide_examples.py` and `test_readme_examples.py` [src:docs/guide/]. No API reference page yet |
| **Packaging** | 🟡 partial | One package, `plugkit` 0.1.0, with honest `config`/`hmr` extras. Unreleased; the PyPI name is claimed but nothing is published. The vendored kernel is a fork, not a dependency [src:src/plugkit/VENDORED.md] |

## The honest read

**Teaching is done for now.** Eight chapters cover the model, the first plugin,
plain components, tools, writing a service, config and reactivity, composition
from a file, and testing. Every example runs in the suite. What is missing is a
generated API reference, which is a packaging job rather than a writing one.

**Conformance is a ceiling, not a gap.** Nine assertions is the right number for
what exists. It grows as services are added, not before.

**signalpy is retired, and this is the evidence.** After four months: 0 stars, 0
forks, 0 watchers, 0 issues; the 14-day clone count of 8 is CI and the author's
own machines. There was no user base to break, so `src/signalpy/` is deleted
rather than deprecated. 0.4.0 remains on PyPI for prismi3, which pins it and
vendors its own copy. Its documentation was removed too, since keeping a book for
a deleted package makes the repository read as two systems; git history holds it
at commit `23d1fdb`.

**The next real risk is Packaging.** The name is claimed, nothing is published,
and until a `pip install plugkit` works the adoptability argument is theoretical.

**Scope is smaller than the predecessor's, on purpose and at a cost.** signalpy
shipped nine providers and three transport adapters; plugkit ships four services
and no transports. Auth, credentials, storage, tracing, workspace and the
REST/MCP/CLI adapters have no replacement. `docs/design/what-it-does-not-replace.qmd`
states this against `dependency-injector`, `pluggy` and `iPOPO` as well. Any
claim that plugkit supersedes those is false and should not appear in the docs.

# History

Dated records. Nothing here describes the current system.

| | |
|---|---|
| `2026-08-23-python-dsh-port-landscape.md` | Survey of the existing Python ports of DeepSeek Harness, with measurements. |

## Removed

**The signalpy documentation.** `signalpy-kernel` 0.4.0 had a 30-page Quarto book
and 4,500 lines of April design notes. All of it described decorators and a
component model that plugkit does not have, and four of the design notes were
about the prismi3 backend rather than this project.

Git has every file:

```bash
git show 23d1fdb:docs/guide/01-first-component.qmd        # a book chapter
git show 34dd902:docs/history/2026-04-design-notes/       # the design notes
git checkout 23d1fdb -- docs/                             # restore the tree locally
```

Two pieces survived into the current docs, because they describe code that still
ships. `concepts/reactive-internals.qmd` became
[`docs/design/reactive-engine.qmd`](../design/reactive-engine.qmd). The iPOPO
parity audit was superseded by
[`docs/design/why-not-ipopo.qmd`](../design/why-not-ipopo.qmd), which was written
by running iPOPO rather than reading about it.

# History

Dated records. Nothing here describes the current system.

| | |
|---|---|
| `2026-04-design-notes/` | Design notes and audits from the signalpy era, April 2026. |

## The retired signalpy documentation

`signalpy-kernel` 0.4.0 had a 30-page Quarto book: eight tutorial chapters, eight
concept pages, ten patterns and four reference pages. All of it documented
decorators and a component model that plugkit does not have.

It was removed rather than kept, because a full book for a deleted package makes
the repository look like two systems. It is in git history at commit `23d1fdb`:

```bash
git show 23d1fdb:docs/guide/01-first-component.qmd
git checkout 23d1fdb -- docs/          # to restore the whole tree locally
```

One page survived into the current docs. `concepts/reactive-internals.qmd`
described the Signal engine, which plugkit still ships as `src/plugkit/signals.py`,
and is now `docs/design/reactive-engine.qmd`.

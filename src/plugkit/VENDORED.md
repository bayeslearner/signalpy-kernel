# `plugkit/cordis` — vendored, with changes

## Where it came from

`src/plugkit/cordis/` is a vendored copy of **[geohotstan/cordis-py]** (MIT), a pure-Python
port of **Cordis 4**, the plugin kernel underneath **[deepseek-ai/deepseek-harness]** (MIT).
Reference source for every semantic decision is `vendor/cordis/src/*.ts` in the harness tree.

[geohotstan/cordis-py]: https://github.com/geohotstan/cordis-py
[deepseek-ai/deepseek-harness]: https://github.com/deepseek-ai/deepseek-harness

Vendored at upstream commit `test(paper): render the Cordis paper as an executable test suite`
(2026-08-14). Its test suite is vendored alongside, under `plugkit/tests/`.

## Why this port and not the others

Three MIT Python ports of Cordis exist. All three pass their own suites; only one passes a
suite written against Cordis's *documented* semantics rather than its own. Measured with
`plugkit/tests/test_conformance.py`:

| | core LOC | own tests | conformance | verdict |
|---|---|---|---|---|
| [geohotstan/cordis-py] | 4,224 | 156 + 2 xfail | **6/9 → 9/9 after one fix** | vendored |
| [ge3m0r/cordis-py](https://github.com/ge3m0r/cordis-py) | 2,651 | 59 | 5/9 | `ctx.effect()` raises `'Symbol' object is not callable`; `isolate()` collides with the root scope |
| [ddebowczyk/cordis-python](https://github.com/ddebowczyk/cordis-python) | 10,654 | ~900 | n/a | re-designed the API (typed tokens, `get`/`require`/`lineage`) — forfeits the point of porting Cordis, which is that dsh's docs stay a valid spec. Its `spec/` is still worth mining as a conformance source. |

## Changes made here

### 1. The dispatch carrier is ambient, not a leading positional argument

Cordis binds the carrier as a listener's `this` (`hook.callback.bind(thisArg)` in
`events.ts:dispatch`), so a listener's parameters are exactly the event arguments. The
upstream port passed the carrier as a leading positional to every listener in all five
dispatch modes, which changes the arity of every listener away from what dsh's plugins and
its documentation assume — `ctx.on('tools/pre-execute', cb)` would need `cb(this, exec)`.

Fixed with a `ContextVar`:

- `cordis/utils.py` — added `this_()`, `call_listener()`, `acall_listener()`
- `cordis/events.py` — all five modes route through them; `internal_listener` and
  `internal_update` read the carrier with `this_()`
- `cordis/reflect.py` — `bind()` traces every argument instead of treating `args[0]` as `this`
- `cordis/loader.py`, `cordis/include.py` — seven internal listeners updated
- `plugkit/tests/` — 16 listeners updated to the Cordis signature

`this_()` is valid during a listener's synchronous body, and across an async listener's own
awaits. A coroutine returned from a sync dispatch mode and awaited elsewhere does not keep it.

### 2. The innermost waterfall default is called with no arguments

TypeScript calls the service's own default with the full argument list and lets it ignore the
extras. Python has no such tolerance, and every real Cordis default is nullary
(`() => ({ kind: 'allow' })`), so `events.waterfall` calls `inner()`. See the comment at the
call site.

### 3. Packaging

Imports are `plugkit.cordis`, not top-level `cordis`, so 1.0 (`src/signalpy`) and 2.0 can be
installed together. Fixture module paths in `tests/fixtures/base.yml` and the `create.py`
scaffold template follow.

## Keeping it in sync

Upstream is a single-author pre-1.0 repo with no releases. Treat this as a fork, not a
dependency. To take upstream changes, diff against the vendored commit above and re-apply the
three changes; `test_conformance.py` is the gate that says whether they still hold.

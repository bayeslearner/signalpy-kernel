# Who has already ported DeepSeek Harness to Python — 2026-08-23

A survey run because plugkit is a kernel with almost nothing on it, and the
obvious next question is whether to build the services or adopt someone's.

**The answer is that several people have already done this, and none of it is
discoverable.** Every measurement below comes from cloning the repository and
running it.

## What exists

| Repository | ★ | Python LOC | Tests run here | What it is |
|---|---|---|---|---|
| [havocio/dsh-python](https://github.com/havocio/dsh-python) | **0** | 34,450 | **381 passed, 4 failed** | "1:1 replica of dsh in Python". Cordis-shaped kernel plus ~35 services and 19 plugins. MIT. |
| [Lxxz666/DSH-wanter-python](https://github.com/Lxxz666/DSH-wanter-python) | **1** | 21,922 | **220 passed, 5 skipped** | 39 subsystem packages matching dsh's layout, on a simplified 921-line kernel. |
| [warmsum/mini-harness](https://github.com/warmsum/mini-harness) | 106 | 17,156 | not run | A book, not a library: 17 chapters building dsh's mechanisms from one model call. |
| [adpanru/cordis-mini](https://github.com/adpanru/cordis-mini) | 25 | 1,299 | not run | Cordis's core in ~600 lines, for teaching. |
| [zhnt/loushang](https://github.com/zhnt/loushang) | 1,217 | 536,956 | not run | A Python agent harness for coding workflows. Not a dsh port. |
| [awesome-dsh-plugin](https://github.com/awesome-dsh-plugin/awesome-dsh-plugin) | 11,786 | — | — | The plugin ecosystem index. TypeScript plugins for the TS runtime. |

The two serious ports have **0 and 1 stars** while the parent project has
187,000. Both were last pushed within three days of this survey.

## havocio/dsh-python, in detail

The closest existing thing to what this project would otherwise build.

**Its kernel is Cordis-shaped.** `dsh_py/core/` holds `context.py`, `events.py`,
`fiber.py`, `reflect.py`, `registry.py`, `service.py`, `signal.py` — the same
decomposition as `vendor/cordis/src`, 1,213 lines. `AppContext` exposes `plugin`,
`provide`, `effect`, `on`, `once`, `emit`, `parallel`, `serial`, `bail`,
`waterfall`, `extend`, `isolate`, `intercept`, `dispose`.

**Verified working:** dependency-driven activation and total unload.

```
with lazy=True:
  mounted, log=[]                       # waited for the dependency
  after db appears, log=['ran']         # activated
unload:
  disposal order=['rel2', 'rel1']       # reverse
  listener gone=True
```

### Its kernel, measured against Cordis

`dsh_py/core/` uses Cordis's filenames. The substance is about a quarter of it,
and the difference is concentrated in the file that matters most.

| | Cordis TS | plugkit | havocio |
|---|---|---|---|
| `fiber` | 754 | 652 | **114** |
| `reflect` | 418 | 216 | 47 |
| `registry` | 337 | 158 | 56 |
| `events` | 352 | 189 | 202 |
| `context` | 146 | 229 | 335 |
| traceable layer | in `reflect` | 251 | none |
| loader / HMR | 1,749 | 1,247 | none |

Behaviour, each run rather than inferred:

| Cordis property | havocio | |
|---|---|---|
| a plugin waits for its dependencies | ✅ | via `lazy=True`; the default raises |
| effects owned by the **caller's** fiber | ✅ | verified — better than the missing traceable layer suggests |
| `isolate()` scopes a service name | ✅ | verified |
| unload is total, disposers in reverse | ✅ | verified |
| **async plugin bodies** | ❌ | `coroutine 'slow' was never awaited`, body never ran |
| **provider swap rebuilds dependents** | ❌ | dispose the provider, mount a replacement: the dependent does not re-run |
| a raising plugin body is contained | ❌ | `context.py:287` calls `apply_fn(self, config)` in a `try/finally` that only pops a stack |
| `FAILED` state | ❌ | four states; nowhere to hang supervision |
| generator effects yielding several disposers | ❌ | `effect()` takes the disposer itself |

The two failures in bold are decisive for an agent runtime.

**Async.** `plugin()` is synchronous. An `async def` body returns a coroutine
that is discarded — the identical failure mode as iPOPO's `@Validate`. An agent
plugin that opens an HTTP session or connects to a database during startup cannot
be written.

**No epoch.** Dependency waiting is a `_pending_plugins` queue drained when
`provide()` is called. It is one-directional: it wakes plugins when a dependency
appears and does nothing when one goes away. So a dependent keeps a stale
reference across an implementation swap, which is the hazard the epoch exists to
prevent. `finalize_pending()` also *raises* if anything is still pending, so
`PENDING` is an error state rather than a resting one — a plugin whose optional
dependency never arrives is a failure rather than a feature left unmounted.

**Coverage:** roughly 35 of dsh's ~47 service concepts, plus 19 plugins including
`tool_bash`, `tool_fs`, `tool_todo`, `guard_timeout`, `guard_repeat_tool`,
`mcp_client`, `subagent`, `long_term_memory`. Absent: sandbox, skills, web, lsp,
`codeRuntime`, `workflowEngine`, `agentTeams`, approval/permission presets.

Internals and error messages are in Chinese.

## Lxxz666/DSH-wanter-python, in detail

39 packages: `agent cli code commands compaction config context cordis credentials
feedback fs goal hooks interaction jobs kernel llm mcp memory persistence plan
preset projection prompt sandbox schedule server session settings skill storage
subagent subprocess telemetry todo tools web workflow workspace`.

Broader service coverage than havocio and a green suite. But its kernel
(`dsh/kernel/`, 921 lines: `context.py events.py loader.py service.py tree.py`)
has **no `Fiber` class and no `isolate`**. It has dsh's *features* on a simpler
substrate, so unload totality and per-agent scoping are not structural
properties there.

Its `dsh/cordis/` is not the kernel — it is the agent-authored-plugin runner,
dsh's `cordis-host-runner` equivalent.

## What this changes

**A claim made earlier in this project needs correcting.** The README says Python
does not have lifetime ownership, citing pluggy, stevedore and the DI containers.
That is true of the *established* ecosystem and false of the frontier: two
unknown repositories have it, one of them faithfully enough to pass the
behavioural checks above.

**It does not change the decision to keep plugkit's kernel.** havocio's is
Cordis-*inspired*: correct on ownership and scoping, absent on async, epoch and
error containment. Those three are not additions to it — the first is a rewrite
of `plugin()` and everything below it. None of the nine rows above would have
been visible from its README, which is what a conformance suite is for.

**It changes what to build next.** Re-deriving ~35 MIT-licensed services would be
waste. The split that plays to each side: plugkit's kernel, havocio's service
implementations as the reference, and only the services a real application uses.
For prismi3 that is roughly eight — agent loop, llm adapter, session persistence,
tools, skills, compaction, subagents, approval — not forty-seven.

**A courtesy worth extending.** havocio pushed 34,000 lines of this three days
before the survey and has no users. Anyone mining the work should say so to them
first.

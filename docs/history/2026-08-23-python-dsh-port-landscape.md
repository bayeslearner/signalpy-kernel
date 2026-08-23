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

**Three divergences from Cordis**, all of which matter:

| | Cordis | havocio |
|---|---|---|
| Unmet dependency | fiber waits in `PENDING` | **raises** `RuntimeError: 插件依赖了尚未可用的服务` unless `lazy=True` |
| Fiber states | 6 — `PENDING LOADING ACTIVE FAILED UNLOADING DISPOSED` | 4 — no `LOADING`, no **`FAILED`** |
| `effect()` | takes an *execute* function that runs and returns a disposer; may be a generator yielding several | takes the disposer directly |

Waiting being opt-in inverts the model: mount order matters again by default,
which is the thing `inject` exists to remove. No `FAILED` state means no place to
hang supervision. And `effect(disposer)` cannot express setup-that-can-fail or an
effect that yields several disposers.

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

**It does not change the decision to keep plugkit's kernel.** havocio's kernel is
Cordis-*inspired*; plugkit's is a Cordis *port* with a conformance suite tested
against the TypeScript. The three divergences above are exactly what such a suite
is for, and none of them would have been visible from the README.

**It changes what to build next.** Re-deriving 35 services that already exist
under MIT would be waste. The service layer is where havocio's work is worth
mining; the kernel is where plugkit's is.

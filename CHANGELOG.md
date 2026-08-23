# Changelog

All notable changes are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions follow [SemVer](https://semver.org/).

## [Unreleased]

Nothing published yet. `pip install plugkit` does not work until 0.1.0 ships.

## [0.1.0] — unreleased

First release under the name `plugkit`. Replaces `signalpy-kernel`, which is
retired — see below.

### Added

- **The kernel**, a vendored port of Cordis: contexts, fibers, reversible
  effects, five event dispatch modes, the plugin registry, the YAML composition
  loader, and hot module replacement. Provenance and every local change in
  `src/plugkit/VENDORED.md`.
- **`provide()` and `@plugin`** — bind a plain class as a service without that
  class importing anything from plugkit. Dependencies may be declared as a list,
  a dict, or a Protocol, in which case `typing.get_protocol_members` derives the
  runtime injection list from the same declaration the type checker uses.
- **`ctx.tools`** — a tool registry with DeepSeek Harness's five-stage pipeline:
  a pre-execute veto, monotonic guards, an execute waterfall for timeouts and
  metrics, a post-execute stage for rewriting or blocking a result, and a frozen
  result event. `Ask` fails closed.
- **`ctx.config`** — YAML, dict, env and pydantic-settings loading via
  `dependency-injector`, with one Signal per dotted key so a write wakes only the
  readers of that key.
- **`ctx.reactive`** — `Signal` / `Computed` / `Effect` bound to fiber lifetime,
  so a subscription dies with the plugin that made it.
- **`ctx.supervisor`** — OTP-style restart strategies (`one_for_one`,
  `one_for_all`, `rest_for_one`) on Cordis's otherwise unused `FAILED` state.
- **`test_conformance.py`** — nine assertions traced to `vendor/cordis/src/*.ts`
  rather than to this implementation. The gate for taking upstream changes, and
  what established that two of the three public Cordis ports are broken.

### Changed from the vendored port

- The dispatch carrier is ambient (`utils.this_`) rather than a leading
  positional argument, so a listener's parameters match Cordis and plugins
  written from dsh's documentation work unmodified.
- The innermost waterfall default is called with no arguments; Python does not
  tolerate the extra arguments TypeScript ignores, and every real Cordis default
  is nullary.
- `Traceable.__getattr__` no longer rebinds callable *data* — a provider, a
  lambda, a partial — as a method on the caller's view. The discriminator is
  whether the name lives in the instance `__dict__`.

### Removed

- **`signalpy`**, the previous design: a reactive component microkernel with
  twelve decorators. Retired 2026-08-23 after four months with zero stars, forks,
  watchers or issues. It had no users, so it was deleted rather than deprecated.
  `signalpy-kernel==0.4.0` remains on PyPI indefinitely. Its documentation is
  preserved under `docs/history/2026-08-v1-book/`.
- The **platform/provider tier**. Config and logging were never system services;
  they are ordinary plugins with no privileged status.
- The **trait system** (L0–L3). Auto-derived labels that nothing consumed for
  behaviour.

### Notes on 0.x

The API is not frozen. `provide()`'s required service-name argument was added
after the defaulted version proved to fail silently on a class rename, and more
of that kind of correction should be expected before 1.0.

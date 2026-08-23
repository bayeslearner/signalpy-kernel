"""Config — the one place `dependency-injector` is worth adopting.

Its `providers.Configuration` is a mature, well-tested loader: YAML, dicts, env
vars with defaults, Pydantic settings, and `.override()` for tests. That is real
work nobody should redo, and 1.0's `ConfigProvider` was a worse version of it.

What it does not do is tell anyone that a value changed — providers are pull-
based. So loading and layering come from `dependency-injector`, and propagation
comes from a `Signal` on top:

    await root.plugin(ReactiveService)
    await root.plugin(ConfigService, {"yaml": "conf/app.yml"})

    def http(ctx, config=None):
        ctx.reactive.effect(lambda: ctx.client.set_timeout(ctx.config.get("http.timeout", 30)))
    http.inject = ["config", "reactive", "client"]

`get()` is a reactive read: called inside a `Computed` or `Effect` it registers a
dependency, so `set()` or a reload re-runs exactly the effects that read the
value — rather than reloading the plugin, which is what routing config through
Cordis's `internal/update` would do.

`dependency-injector` is optional. Without it the service still works from dicts
and YAML; only `from_env`/`from_pydantic`/`override` need the package.
"""

from __future__ import annotations

import logging
from typing import Any

from ..signals import Signal
from ..cordis import Service

log = logging.getLogger(__name__)

__all__ = ["ConfigService", "MISSING"]

MISSING = object()

try:  # pragma: no cover - exercised by whichever branch is installed
    from dependency_injector import providers as _di_providers
except ImportError:  # pragma: no cover
    _di_providers = None


def _dig(data: dict, key: str, default: Any) -> Any:
    """Read a dotted key out of a nested dict."""
    node: Any = data
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def _bury(data: dict, key: str, value: Any) -> dict:
    """Return a copy of `data` with a dotted key set. Never mutates the input.

    Copying matters: `Signal.set` compares identity to decide whether to notify,
    and an in-place mutation would be invisible to every reactive reader.
    """
    out = dict(data)
    node = out
    parts = key.split(".")
    for part in parts[:-1]:
        child = node.get(part)
        node[part] = dict(child) if isinstance(child, dict) else {}
        node = node[part]
    node[parts[-1]] = value
    return out


class ConfigService(Service):
    """Provides `ctx.config`.

    Config keys accepted at mount time:

        yaml      path to a YAML file, or a list of paths layered in order
        dict      a literal dict, applied after any YAML
        required  bool — raise if a YAML path is missing (default False)
    """

    provide = "config"

    def __init__(self, ctx, config=None):
        super().__init__(ctx)
        options = config or {}
        self._di = _di_providers.Configuration() if _di_providers else None
        self._plain: dict = {}
        self._data: Signal[dict] = Signal({})
        # One Signal per dotted key that anyone has actually read, so a change
        # wakes only the readers of *that* key. A single Signal over the whole
        # dict would wake every config reader on every write, which is the
        # behaviour this service exists to avoid.
        self._keys: dict[str, Signal] = {}

        paths = options.get("yaml") or []
        if isinstance(paths, str):
            paths = [paths]
        for path in paths:
            self.load_yaml(path, required=options.get("required", False))
        if options.get("dict"):
            self.load_dict(options["dict"])

    # ── reading ───────────────────────────────────────────────────────

    def get(self, key: str, default: Any = None) -> Any:
        """Read a dotted key. Reactive — tracked inside a Computed or Effect.

        The default is applied at read time rather than stored, so two callers
        reading the same key with different defaults do not fight.
        """
        value = self.signal_for(key).get()
        return default if value is MISSING else value

    def require(self, key: str) -> Any:
        """Read a dotted key, raising if it is absent. Reactive."""
        value = self.signal_for(key).get()
        if value is MISSING:
            raise KeyError(f"required config key {key!r} is not set")
        return value

    def peek(self, key: str, default: Any = None) -> Any:
        """Read without registering a reactive dependency."""
        return _dig(self._plain, key, default)

    def all(self) -> dict:
        """The whole materialised config. Reactive — wakes on any change."""
        return self._data.get()

    def signal_for(self, key: str) -> Signal:
        """The Signal behind one dotted key, created on first read.

        Holds `MISSING` when the key is absent, so "unset" and "set to None"
        stay distinguishable.
        """
        signal = self._keys.get(key)
        if signal is None:
            signal = Signal(_dig(self._plain, key, MISSING))
            self._keys[key] = signal
        return signal

    # ── writing ───────────────────────────────────────────────────────

    def set(self, key: str, value: Any) -> None:
        """Set a dotted key and wake every reactive reader of it."""
        self._plain = _bury(self._plain, key, value)
        self._republish()

    # ── loading ───────────────────────────────────────────────────────

    def load_dict(self, data: dict) -> None:
        if self._di is not None:
            self._di.from_dict(data)
        self._plain = _merge(self._plain, data)
        self._republish()

    def load_yaml(self, path: str, *, required: bool = False) -> None:
        if self._di is not None:
            self._di.from_yaml(path, required=required)
            self._plain = _merge(self._plain, self._di() or {})
        else:
            import os

            if not os.path.exists(path):
                if required:
                    raise FileNotFoundError(path)
                log.warning("config: %s not found, skipping", path)
                return
            import yaml

            with open(path, encoding="utf-8") as handle:
                self._plain = _merge(self._plain, yaml.safe_load(handle) or {})
        self._republish()

    def load_env(self, key: str, env_var: str, default: Any = None) -> None:
        """Bind one dotted key to an environment variable. Needs dependency-injector."""
        self._require_di("load_env")
        node = self._di
        for part in key.split("."):
            node = getattr(node, part)
        node.from_env(env_var, default)
        self._plain = _merge(self._plain, self._di() or {})
        self._republish()

    def load_pydantic(self, settings: Any) -> None:
        """Populate from a pydantic-settings instance. Needs dependency-injector."""
        self._require_di("load_pydantic")
        self._di.from_pydantic(settings)
        self._plain = _merge(self._plain, self._di() or {})
        self._republish()

    def override(self, data: dict):
        """Context manager that temporarily replaces config. For tests."""
        self._require_di("override")
        service = self

        class _Override:
            def __enter__(self_inner):
                self_inner._saved = service._plain
                self_inner._ctx = service._di.override(data)
                self_inner._ctx.__enter__() if hasattr(self_inner._ctx, "__enter__") else None
                service._plain = _merge(service._plain, data)
                service._republish()
                return service

            def __exit__(self_inner, *exc):
                service._di.reset_override()
                service._plain = self_inner._saved
                service._republish()
                return False

        return _Override()

    # ── internals ─────────────────────────────────────────────────────

    def _republish(self) -> None:
        snapshot = dict(self._plain)
        self._data.set(snapshot)
        # Compare by equality, not the Signal's identity check: a reload that
        # produces an equal value must not wake anyone.
        for key, signal in self._keys.items():
            new = _dig(snapshot, key, MISSING)
            if signal.peek() != new:
                signal.set(new)

    def _require_di(self, what: str) -> None:
        if self._di is None:
            raise RuntimeError(
                f"ConfigService.{what}() needs the `dependency-injector` package "
                "(pip install 'signalpy-kernel[config]')"
            )


def _merge(base: dict, incoming: dict) -> dict:
    """Deep-merge `incoming` over `base`, returning a new dict."""
    out = dict(base)
    for key, value in (incoming or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out

"""Tool plugins. Each module has `register(server, settings, log) -> object | None`.

files, sessions — read-only (default). memory — append-only notes. delegation — background tasks (opt-in).
"""

from __future__ import annotations

from importlib import import_module

AVAILABLE = ("files", "sessions", "memory", "delegation")


def register_all(server, settings, log) -> dict:
    loaded = {}
    for name in settings.plugins:
        if name not in AVAILABLE:
            raise ValueError(f"unknown plugin {name!r}; available: {', '.join(AVAILABLE)}")
        loaded[name] = import_module(f"mcp_gateway.plugins.{name}").register(server, settings, log)
    return loaded

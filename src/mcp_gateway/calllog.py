"""Audit log: one JSONL line per tool call, so what the model did is checked from the log, not from its words."""

from __future__ import annotations

import functools
import inspect
import json
import threading
import time
from pathlib import Path


class CallLog:
    def __init__(self, path: Path, max_value_chars: int = 500):
        self.path = path
        self.max_value_chars = max_value_chars
        self._lock = threading.Lock()

    def write(self, tool: str, **args) -> None:
        args = {k: (v[: self.max_value_chars] if isinstance(v, str) else v) for k, v in args.items()}
        line = json.dumps({"ts": time.strftime("%F %T"), "tool": tool, **args}, ensure_ascii=False, default=str)
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a") as f:
                f.write(line + "\n")

    def read(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text().splitlines() if line.strip()]


def logged_tool(server, log: CallLog):
    """Like `@server.tool()`, but every call is written to the call log first (with its arguments)."""

    def deco(fn):
        sig = inspect.signature(fn)

        @functools.wraps(fn)
        def wrapper(*a, **kw):
            bound = sig.bind(*a, **kw)
            bound.apply_defaults()
            log.write(fn.__name__, **bound.arguments)
            return fn(*a, **kw)

        server.tool()(wrapper)
        return wrapper

    return deco

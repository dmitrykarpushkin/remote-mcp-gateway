"""Shared memory across conversations: an append-only Markdown file of dated notes."""

from __future__ import annotations

import threading
import time
from pathlib import Path


class Memory:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()

    def text(self) -> str:
        return self.path.read_text() if self.path.exists() else ""

    def remember(self, note: str) -> None:
        note = " ".join(note.split())
        if not note:
            raise ValueError("empty note")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self.path.open("a") as f:
            f.write(f"- [{time.strftime('%Y-%m-%d')}] {note}\n")


def register(server, settings, log) -> Memory:
    memory = Memory(settings.state_dir / "memory.md")
    tool = server.tool

    @tool
    def memory_read() -> str:
        """What the assistant knows about the user's affairs: promises, plans, ideas, people, decisions.
        Call before answering about their plans or ongoing work."""
        return memory.text() or "(memory is empty)"

    @tool
    def memory_remember(note: str) -> str:
        """Remember a fact (a promise, plan, idea, person, decision) for all future conversations.
        Write it self-contained, with absolute dates."""
        memory.remember(note)
        return "Remembered."

    return memory

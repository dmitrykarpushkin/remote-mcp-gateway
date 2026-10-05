"""Optional plugin: hand work to background agents and read the results back.

A voice or chat model calls `delegate_task`; the task lands in a JSON store and a worker thread wakes the
executors through a pluggable dispatcher. Executors (other agent sessions connected to the same gateway) take
the task with `pending_tasks`, do it, and close it with `report_result`; the caller sees it in `task_updates`.

  caller --delegate_task--> TaskStore --worker--> Dispatcher.fire() --> executor wakes
  executor --pending_tasks / report_result--> TaskStore --task_updates--> caller

Dispatchers: `none` (executors poll), `command` (run any argv; the task text goes to stdin), `claude-trigger`
(fire a saved Claude Code remote trigger by id through the headless `claude` CLI). The trigger carries a fixed
message; tasks never travel inside it, they wait in the store, so a spare fire is harmless.
"""

from __future__ import annotations

import json
import queue
import secrets
import subprocess
import threading
import time
from pathlib import Path
from typing import Protocol


STATUSES = ("queued", "sent", "not_sent", "in_progress", "done", "failed", "needs_you")
FINAL = {"done", "failed", "needs_you"}


class TaskStore:
    """Tasks in one JSON file, written atomically, guarded by a lock."""

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()

    def _load(self) -> dict:
        return json.loads(self.path.read_text()) if self.path.exists() else {}

    def _save(self, tasks: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(tasks, ensure_ascii=False, indent=1))
        tmp.replace(self.path)

    def create(self, text: str) -> str:
        task_id = "t" + secrets.token_hex(3)
        with self._lock:
            tasks = self._load()
            tasks[task_id] = {"id": task_id, "task": text, "status": "queued", "created": time.strftime("%F %T")}
            self._save(tasks)
        return task_id

    def get(self, task_id: str) -> dict | None:
        return self._load().get(task_id)

    def update(self, task_id: str, **fields) -> bool:
        with self._lock:
            tasks = self._load()
            if task_id not in tasks:
                return False
            tasks[task_id].update(fields, updated=time.strftime("%F %T"))
            self._save(tasks)
        return True

    def take_pending(self) -> list[dict]:
        """Tasks no executor has taken yet; marks them in_progress."""
        with self._lock:
            tasks = self._load()
            out = [t for t in tasks.values() if t.get("status") in ("queued", "sent", "not_sent")]
            for t in out:
                t.update(status="in_progress", updated=time.strftime("%F %T"))
            self._save(tasks)
        return out

    def recent(self, limit: int = 5) -> list[dict]:
        return sorted(self._load().values(), key=lambda t: (t.get("created", ""), t["id"]), reverse=True)[:limit]

    def queued_ids(self) -> list[str]:
        return [t["id"] for t in self._load().values() if t.get("status") == "queued"]


class Dispatcher(Protocol):
    def fire(self, task: dict) -> tuple[bool, str]: ...


class NoDispatcher:
    """Executors poll `pending_tasks` themselves."""

    def fire(self, task: dict) -> tuple[bool, str]:
        return True, "queued for polling executors"


class CommandDispatcher:
    """Runs an argv per task (a webhook call, a queue publisher, `claude -p ...`); the task text goes to stdin."""

    def __init__(self, argv: list[str], timeout: float = 120, run=subprocess.run):
        if not argv:
            raise ValueError("command dispatcher needs [delegation].command")
        self.argv, self.timeout, self.run = argv, timeout, run

    def fire(self, task: dict) -> tuple[bool, str]:
        try:
            r = self.run(self.argv, input=task["task"], capture_output=True, text=True, timeout=self.timeout)
        except Exception as e:  # noqa: BLE001 - any failure is reported back to the caller
            return False, f"{type(e).__name__}: {e}"
        return r.returncode == 0, (r.stdout or r.stderr or "").strip()[:300]


class ClaudeTriggerDispatcher:
    """Fires a saved Claude Code remote trigger via the headless CLI and the user's own login.

    The trigger API is reachable only with the user's claude.ai session, so the gateway never handles tokens:
    a cheap model gets exactly one allowed tool (RemoteTrigger) and one instruction.
    """

    def __init__(self, trigger_id: str, claude_bin: str = "claude", model: str = "haiku", run=subprocess.run):
        if not trigger_id:
            raise ValueError("claude-trigger dispatcher needs [delegation].trigger_id")
        self.trigger_id, self.claude_bin, self.model, self.run = trigger_id, claude_bin, model, run

    def fire(self, task: dict) -> tuple[bool, str]:
        prompt = (
            f"Call the RemoteTrigger tool once with action=run and trigger_id={self.trigger_id}. "
            "Reply with exactly OK if it returned HTTP 200, otherwise ERROR: <short reason>."
        )
        argv = [self.claude_bin, "-p", "--model", self.model, "--allowedTools", "RemoteTrigger"]
        try:
            r = self.run([*argv, "--output-format", "json", prompt], capture_output=True, text=True, timeout=120)
            result = json.loads(r.stdout).get("result", "").strip()
        except Exception as e:  # noqa: BLE001
            return False, f"{type(e).__name__}: {e}"
        return result.startswith("OK"), result[:300]


def make_dispatcher(c) -> Dispatcher:
    if c.dispatcher == "none":
        return NoDispatcher()
    if c.dispatcher == "command":
        return CommandDispatcher(c.command)
    if c.dispatcher == "claude-trigger":
        return ClaudeTriggerDispatcher(c.trigger_id, c.claude_bin, c.fire_model)
    raise ValueError(f"unknown dispatcher {c.dispatcher!r}")


class Delegation:
    def __init__(self, store: TaskStore, dispatcher: Dispatcher, retries: int = 1):
        self.store, self.dispatcher, self.retries = store, dispatcher, retries
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._thread: threading.Thread | None = None

    def submit(self, text: str) -> str:
        task_id = self.store.create(text)
        self._queue.put(task_id)
        return task_id

    def dispatch(self, task_id: str) -> None:
        task = self.store.get(task_id)
        if not task or task.get("status") != "queued":
            return
        t0 = time.monotonic()
        ok, info = self.dispatcher.fire(task)
        for _ in range(self.retries):  # headless models occasionally fumble the tool call; a spare fire is harmless
            if ok:
                break
            ok, info = self.dispatcher.fire(task)
        self.store.update(
            task_id, status="sent" if ok else "not_sent", fire_info=info, fire_secs=round(time.monotonic() - t0, 1)
        )

    def _work(self) -> None:
        while (task_id := self._queue.get()) is not None:
            self.dispatch(task_id)

    def start(self) -> None:
        for task_id in self.store.queued_ids():  # re-queue what a restart interrupted
            self._queue.put(task_id)
        self._thread = threading.Thread(target=self._work, daemon=True, name="delegation-worker")
        self._thread.start()

    def stop(self) -> None:
        self._queue.put(None)
        if self._thread:
            self._thread.join(timeout=5)


LABELS = {
    "queued": "queued",
    "sent": "sent",
    "in_progress": "in progress",
    "not_sent": "could not dispatch",
    "done": "done",
    "failed": "failed",
    "needs_you": "needs your decision",
}


def format_updates(tasks: list[dict]) -> str:
    if not tasks:
        return "No tasks yet."
    out = []
    for t in tasks:
        line = f"[{t['id']}] {t['task']} — {LABELS.get(t['status'], t['status'])} (since {t['created'][11:16]})"
        if t.get("result"):
            line += f"\n  result: {t['result']}"
        elif t["status"] == "not_sent":
            line += f"\n  reason: {t.get('fire_info', '')}"
        out.append(line)
    return "\n".join(out)


def register(server, settings, log) -> Delegation:
    c = settings.delegation
    delegation = Delegation(TaskStore(settings.state_dir / "tasks.json"), make_dispatcher(c), c.retries)
    tool = server.tool

    @tool
    def delegate_task(task: str) -> str:
        """Delegate work that needs doing rather than answering (act, check, research, prepare). Returns at once;
        the result appears in task_updates. Only for the conversation with the user, never from executors."""
        task_id = delegation.submit(task)
        return f"Accepted (id {task_id}). The result will appear in task_updates."

    @tool
    def task_updates(limit: int = 5) -> str:
        """Status and results of delegated tasks: queued, sent, in progress, done, failed, needs your decision."""
        return format_updates(delegation.store.recent(max(1, min(limit, 20))))

    @tool
    def pending_tasks() -> str:
        """For executors: take new delegated tasks and mark them in progress. Do each one, then report_result."""
        tasks = delegation.store.take_pending()
        return "\n".join(f"task_id={t['id']}: {t['task']}" for t in tasks) or "No new tasks."

    @tool
    def report_result(task_id: str, status: str, summary: str) -> str:
        """For executors: report the outcome of a task. status is done, failed or needs_you; summary is 1-3
        plain sentences for the user."""
        if status not in FINAL:
            return "status must be done, failed or needs_you"
        ok = delegation.store.update(task_id, status=status, result=summary)
        return "Recorded." if ok else f"No task {task_id}."

    return delegation

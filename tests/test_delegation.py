import json
import subprocess
from types import SimpleNamespace

import pytest

from mcp_gateway.plugins.delegation import (
    ClaudeTriggerDispatcher,
    CommandDispatcher,
    Delegation,
    NoDispatcher,
    TaskStore,
    format_updates,
    make_dispatcher,
)


class Flaky:
    def __init__(self, results):
        self.results = list(results)
        self.calls = 0

    def fire(self, task):
        self.calls += 1
        return self.results.pop(0)


def test_store_lifecycle(tmp_path):
    store = TaskStore(tmp_path / "tasks.json")
    tid = store.create("check the backups")
    assert store.get(tid)["status"] == "queued"
    taken = store.take_pending()
    assert [t["id"] for t in taken] == [tid]
    assert store.get(tid)["status"] == "in_progress"
    assert store.take_pending() == []
    assert store.update(tid, status="done", result="all good")
    assert not store.update("nope", status="done")
    assert "result: all good" in format_updates(store.recent())
    assert not (tmp_path / "tasks.tmp").exists()


def test_dispatch_retries_once_then_records(tmp_path):
    store = TaskStore(tmp_path / "t.json")
    d = Delegation(store, Flaky([(False, "fumbled"), (True, "OK")]), retries=1)
    tid = d.submit("x")
    d.dispatch(tid)
    t = store.get(tid)
    assert t["status"] == "sent" and t["fire_info"] == "OK"


def test_dispatch_failure_is_visible(tmp_path):
    store = TaskStore(tmp_path / "t.json")
    disp = Flaky([(False, "e1"), (False, "e2")])
    d = Delegation(store, disp, retries=1)
    tid = d.submit("x")
    d.dispatch(tid)
    assert disp.calls == 2
    assert store.get(tid)["status"] == "not_sent"
    assert "reason: e2" in format_updates(store.recent())
    # an executor polling later still gets it
    assert [t["id"] for t in store.take_pending()] == [tid]


def test_dispatch_skips_non_queued(tmp_path):
    store = TaskStore(tmp_path / "t.json")
    disp = Flaky([])
    d = Delegation(store, disp)
    tid = store.create("x")
    store.update(tid, status="done")
    d.dispatch(tid)
    d.dispatch("missing")
    assert disp.calls == 0


def test_worker_thread_and_restart_requeue(tmp_path):
    store = TaskStore(tmp_path / "t.json")
    tid = store.create("left over from a restart")
    d = Delegation(store, NoDispatcher())
    d.start()
    tid2 = d.submit("new")
    d.stop()
    assert store.get(tid)["status"] == "sent"
    assert store.get(tid2)["status"] == "sent"


def test_command_dispatcher_passes_task_on_stdin():
    seen = {}

    def run(argv, **kw):
        seen.update(argv=argv, input=kw["input"])
        return SimpleNamespace(returncode=0, stdout="queued 42\n", stderr="")

    ok, info = CommandDispatcher(["notify"], run=run).fire({"task": "do it"})
    assert ok and info == "queued 42"
    assert seen == {"argv": ["notify"], "input": "do it"}


def test_command_dispatcher_reports_errors():
    def boom(argv, **kw):
        raise subprocess.TimeoutExpired(argv, 1)

    ok, info = CommandDispatcher(["x"], run=boom).fire({"task": "t"})
    assert not ok and info.startswith("TimeoutExpired")


def test_claude_trigger_dispatcher():
    captured = {}

    def run(argv, **kw):
        captured["argv"] = argv
        return SimpleNamespace(stdout=json.dumps({"result": "OK"}), returncode=0)

    ok, _ = ClaudeTriggerDispatcher("trig_1", run=run).fire({"task": "secret task text"})
    assert ok
    assert "trigger_id=trig_1" in captured["argv"][-1]
    assert "secret task text" not in " ".join(captured["argv"])  # tasks never travel in the trigger
    assert captured["argv"][captured["argv"].index("--allowedTools") + 1] == "RemoteTrigger"

    bad = ClaudeTriggerDispatcher("t", run=lambda a, **k: SimpleNamespace(stdout="not json"))
    assert bad.fire({"task": "x"})[0] is False


def test_make_dispatcher_validates():
    c = SimpleNamespace(dispatcher="claude-trigger", trigger_id="", claude_bin="claude", fire_model="haiku")
    with pytest.raises(ValueError):
        make_dispatcher(c)
    with pytest.raises(ValueError):
        make_dispatcher(SimpleNamespace(dispatcher="carrier-pigeon"))
    assert isinstance(make_dispatcher(SimpleNamespace(dispatcher="none")), NoDispatcher)

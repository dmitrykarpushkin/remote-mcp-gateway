import json
import time

from mcp_gateway.plugins.sessions import Sessions, ago, read_transcript

CWD = "/work/website"


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def transcript_rows():
    return [
        {"type": "ai-title", "aiTitle": "Fix the footer"},
        {"type": "user", "origin": {"kind": "human"}, "message": {"content": "please fix the footer"}},
        {
            "type": "user",
            "origin": {"kind": "human"},
            "message": {"content": "<system-reminder>skip</system-reminder>"},
        },
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "text", "text": "Looking at it."},
                    {"type": "tool_use", "id": "a", "name": "Read"},
                    {"type": "tool_use", "id": "b", "name": "Edit"},
                ]
            },
        },
        {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "a"}]}},
        {"type": "assistant", "isSidechain": True, "message": {"content": [{"type": "text", "text": "sub-agent"}]}},
        "not json",
    ]


def setup_home(tmp_path):
    home = tmp_path / ".claude"
    tdir = home / "projects" / CWD.replace("/", "-")
    rows = transcript_rows()
    tdir.mkdir(parents=True)
    (tdir / "live1.jsonl").write_text("\n".join(r if isinstance(r, str) else json.dumps(r) for r in rows))
    write_jsonl(tdir / "old1.jsonl", [{"type": "ai-title", "aiTitle": "Closed one"}])
    (home / "sessions").mkdir()
    (home / "sessions" / "1.json").write_text(
        json.dumps({"cwd": CWD, "sessionId": "live1", "pid": 111, "status": "idle", "updatedAt": time.time() * 1000})
    )
    (home / "sessions" / "2.json").write_text(json.dumps({"cwd": "/elsewhere", "sessionId": "x", "pid": 111}))
    return home


def test_read_transcript(tmp_path):
    p = tmp_path / "t.jsonl"
    p.write_text("\n".join(r if isinstance(r, str) else json.dumps(r) for r in transcript_rows()))
    t = read_transcript(p)
    assert t["title"] == "Fix the footer"
    assert t["prompts"] == ["please fix the footer"]
    assert t["last_text"] == "Looking at it."
    assert t["pending"] == ["Edit"]


def test_overview_lists_live_then_closed_only_for_configured_projects(tmp_path):
    s = Sessions(setup_home(tmp_path), {CWD: "website"}, pid_alive=lambda pid: pid == 111)
    sessions = s.collect()
    assert [(x["sid"], x["live"]) for x in sessions] == [("live1", True), ("old1", False)]
    text = s.overview()
    assert "[website] Fix the footer — waiting for you" in text
    assert "unfinished tool calls (may wait for permission): Edit" in text
    assert "Closed one — closed" in text


def test_dead_pid_is_not_live(tmp_path):
    s = Sessions(setup_home(tmp_path), {CWD: "website"}, pid_alive=lambda pid: False)
    assert all(not x["live"] for x in s.collect())


def test_detail_and_unknown_project(tmp_path):
    s = Sessions(setup_home(tmp_path), {CWD: "web-site"}, pid_alive=lambda pid: True)
    assert "you wrote: please fix the footer" in s.detail("website")
    assert "Known projects: web-site" in s.detail("mobile")


def test_empty(tmp_path):
    (tmp_path / "sessions").mkdir()
    assert Sessions(tmp_path, {}).overview().startswith("No live sessions")


def test_ago():
    now = 100_000.0
    assert ago(now, now) == "just now"
    assert ago(now - 5 * 60, now) == "5 min ago"
    assert ago(now - 3 * 3600, now) == "3 h ago"
    assert ago(now - 72 * 3600, now) == "3 d ago"

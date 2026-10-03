"""Read-only overview of Claude Code sessions on this machine: which are live, busy, or waiting for the user.

Reads the session registry (`<claude_home>/sessions/*.json`) and transcripts
(`<claude_home>/projects/<cwd with / replaced by ->/<session>.jsonl`), only for the project folders listed in
the config.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from ..calllog import logged_tool

STATUS = {"idle": "waiting for you", "busy": "working", "shell": "open (shell)"}


def ago(epoch: float, now: float | None = None) -> str:
    m = int(((now or time.time()) - epoch) // 60)
    if m < 1:
        return "just now"
    if m < 60:
        return f"{m} min ago"
    h = m // 60
    return f"{h} h ago" if h < 48 else f"{h // 24} d ago"


def text_of(content) -> str:
    if isinstance(content, str):
        return content
    return "\n".join(c.get("text", "") for c in content or [] if isinstance(c, dict) and c.get("type") == "text")


def read_transcript(path: Path) -> dict:
    """Title, the user's prompts, the agent's last text, and tool calls still waiting for a result."""
    title, prompts, last_text, open_tools = None, [], "", {}
    for line in path.open(errors="replace"):
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("type") == "ai-title":
            title = e.get("aiTitle")
        if e.get("isSidechain"):
            continue
        msg = e.get("message") or {}
        if e.get("type") == "user":
            content = msg.get("content")
            if isinstance(content, list):
                for c in content:
                    if isinstance(c, dict) and c.get("type") == "tool_result":
                        open_tools.pop(c.get("tool_use_id"), None)
            if (e.get("origin") or {}).get("kind") == "human" or e.get("turnOrigin") == "human":
                t = text_of(content).strip()
                if t and not t.startswith("<"):
                    prompts.append(t)
        elif e.get("type") == "assistant":
            for c in msg.get("content") or []:
                if c.get("type") == "text" and c.get("text", "").strip():
                    last_text = c["text"].strip()
                elif c.get("type") == "tool_use":
                    open_tools[c.get("id")] = c.get("name")
    return {"title": title, "prompts": prompts, "last_text": last_text, "pending": list(open_tools.values())}


class Sessions:
    def __init__(self, claude_home: Path, projects: dict[str, str], recent_hours: int = 24, pid_alive=None):
        self.home = claude_home
        self.projects = projects
        self.recent_hours = recent_hours
        self.pid_alive = pid_alive or (lambda pid: pid is not None and os.path.exists(f"/proc/{pid}"))

    def transcript_path(self, cwd: str, session_id: str) -> Path:
        return self.home / "projects" / cwd.replace("/", "-") / f"{session_id}.jsonl"

    def collect(self) -> list[dict]:
        """Live sessions from the registry plus sessions touched in the last `recent_hours`."""
        out, seen = [], set()
        for f in sorted((self.home / "sessions").glob("*.json")):
            try:
                d = json.loads(f.read_text())
            except ValueError:
                continue
            cwd, sid = d.get("cwd", ""), d.get("sessionId")
            if cwd not in self.projects or not sid or not self.pid_alive(d.get("pid")):
                continue
            seen.add(sid)
            out.append(
                {
                    "project": self.projects[cwd],
                    "sid": sid,
                    "name": d.get("name"),
                    "live": True,
                    "status": d.get("status"),
                    "updated": d.get("updatedAt", 0) / 1000,
                    "path": self.transcript_path(cwd, sid),
                }
            )
        cut = time.time() - self.recent_hours * 3600
        for cwd, project in self.projects.items():
            for p in (self.home / "projects" / cwd.replace("/", "-")).glob("*.jsonl"):
                if p.stem in seen or p.stat().st_mtime < cut:
                    continue
                out.append(
                    {
                        "project": project,
                        "sid": p.stem,
                        "name": None,
                        "live": False,
                        "status": "closed",
                        "updated": p.stat().st_mtime,
                        "path": p,
                    }
                )
        rank = {"idle": 0, "busy": 1, "shell": 2}
        out.sort(key=lambda s: (rank.get(s["status"], 3) if s["live"] else 4, -s["updated"]))
        return out

    def describe(self, s: dict, long: bool = False) -> str:
        empty = {"title": None, "prompts": [], "last_text": "", "pending": []}
        t = read_transcript(s["path"]) if s["path"].exists() else empty
        status = STATUS.get(s["status"], s["status"])
        lines = [f"[{s['project']}] {t['title'] or s['name'] or s['sid'][:8]} — {status}, active {ago(s['updated'])}"]
        for p in t["prompts"][-(5 if long else 1) :]:
            lines.append(f"  you wrote: {p[: 600 if long else 200]}")
        if t["last_text"]:
            lines.append(f"  agent said last: {t['last_text'][-1500 if long else -300 :]}")
        if t["pending"] and s["live"]:
            lines.append(f"  unfinished tool calls (may wait for permission): {', '.join(t['pending'][-3:])}")
        return "\n".join(lines)

    def overview(self) -> str:
        sessions = self.collect()
        if not sessions:
            return f"No live sessions and no activity in the last {self.recent_hours} hours."
        live = [s for s in sessions if s["live"]]
        closed = [s for s in sessions if not s["live"]][:4]
        return "\n\n".join(self.describe(s) for s in live + closed)

    def detail(self, project: str) -> str:
        q = project.lower().replace(" ", "").replace("-", "")
        matches = [s for s in self.collect() if q in s["project"].lower().replace("-", "")]
        if not matches:
            names = ", ".join(sorted(set(self.projects.values()))) or "none configured"
            return f"No sessions for project {project!r}. Known projects: {names}."
        return self.describe(matches[0], long=True)


def register(server, settings, log) -> Sessions:
    c = settings.sessions
    sessions = Sessions(c.claude_home, c.projects, c.recent_hours)
    tool = logged_tool(server, log)

    @tool
    def sessions_overview() -> str:
        """Status of the Claude Code sessions on this machine: which are open, what they are doing, which are
        waiting for the user's reply. Live sessions plus ones closed recently."""
        return sessions.overview()

    @tool
    def session_detail(project: str) -> str:
        """The latest Claude Code session of one project: the user's recent requests and the agent's last answer."""
        return sessions.detail(project)

    return sessions

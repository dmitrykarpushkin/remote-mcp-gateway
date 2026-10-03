"""Settings: a TOML file (GATEWAY_CONFIG, see gateway.example.toml) with environment overrides."""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class FilesConfig:
    root: Path = Path(".")
    hidden: tuple[str, ...] = ("__pycache__", "node_modules", "logs")
    max_chars: int = 8000
    max_entries: int = 200


@dataclass(frozen=True)
class SessionsConfig:
    claude_home: Path = Path.home() / ".claude"
    projects: dict[str, str] = field(default_factory=dict)  # session cwd -> project name
    recent_hours: int = 24


@dataclass(frozen=True)
class DelegationConfig:
    dispatcher: str = "none"  # none | command | claude-trigger
    command: list[str] = field(default_factory=list)  # for "command": argv, gets the task text on stdin
    trigger_id: str = ""  # for "claude-trigger"
    claude_bin: str = "claude"
    fire_model: str = "haiku"
    retries: int = 1


@dataclass(frozen=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 8766
    name: str = "gateway"
    instructions: str = "Read-only tools for an assistant. Every call is logged."
    state_dir: Path = Path(".state")
    plugins: tuple[str, ...] = ("files", "sessions")
    path_key: bool = False  # also accept the key as the first URL segment: /<key>/mcp
    files: FilesConfig = field(default_factory=FilesConfig)
    sessions: SessionsConfig = field(default_factory=SessionsConfig)
    delegation: DelegationConfig = field(default_factory=DelegationConfig)

    @property
    def key_file(self) -> Path:
        return self.state_dir / "key"

    @property
    def calls_log(self) -> Path:
        return self.state_dir / "calls.jsonl"

    @classmethod
    def load(cls, env: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env
        data: dict = {}
        if env.get("GATEWAY_CONFIG"):
            data = tomllib.loads(Path(env["GATEWAY_CONFIG"]).read_text())
        g = data.get("gateway", {})
        f, s, d = data.get("files", {}), data.get("sessions", {}), data.get("delegation", {})
        plugins = env.get("GATEWAY_PLUGINS") or ",".join(g.get("plugins", cls.plugins))
        base = cls()
        return cls(
            host=env.get("GATEWAY_HOST", g.get("host", base.host)),
            port=int(env.get("GATEWAY_PORT", g.get("port", base.port))),
            name=g.get("name", base.name),
            instructions=g.get("instructions", base.instructions),
            state_dir=Path(env.get("GATEWAY_STATE_DIR", g.get("state_dir", str(base.state_dir)))).expanduser(),
            plugins=tuple(p.strip() for p in plugins.split(",") if p.strip()),
            path_key=str(env.get("GATEWAY_PATH_KEY", g.get("path_key", False))).lower() in ("1", "true", "yes"),
            files=FilesConfig(
                root=Path(env.get("GATEWAY_FILES_ROOT", f.get("root", "."))).expanduser().resolve(),
                hidden=tuple(f.get("hidden", FilesConfig.hidden)),
                max_chars=int(f.get("max_chars", FilesConfig.max_chars)),
                max_entries=int(f.get("max_entries", FilesConfig.max_entries)),
            ),
            sessions=SessionsConfig(
                claude_home=Path(s.get("claude_home", str(SessionsConfig.claude_home))).expanduser(),
                projects={str(Path(k).expanduser()): v for k, v in s.get("projects", {}).items()},
                recent_hours=int(s.get("recent_hours", 24)),
            ),
            delegation=DelegationConfig(
                dispatcher=env.get("GATEWAY_DISPATCHER", d.get("dispatcher", "none")),
                command=list(d.get("command", [])),
                trigger_id=env.get("GATEWAY_TRIGGER_ID", d.get("trigger_id", "")),
                claude_bin=d.get("claude_bin", "claude"),
                fire_model=d.get("fire_model", "haiku"),
                retries=int(d.get("retries", 1)),
            ),
        )

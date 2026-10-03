from dataclasses import replace

import pytest

from mcp_gateway.config import FilesConfig, Settings
from mcp_gateway.server import build


def settings(tmp_path, plugins):
    (tmp_path / "ws").mkdir(exist_ok=True)
    (tmp_path / "ws" / "hello.md").write_text("hi")
    return replace(Settings(), state_dir=tmp_path / "state", plugins=plugins, files=FilesConfig(root=tmp_path / "ws"))


async def tool_names(server):
    return sorted(t.name for t in await server.list_tools())


async def test_default_plugins_are_read_only(tmp_path):
    server, _, _ = build(settings(tmp_path, ("files", "sessions")))
    assert await tool_names(server) == ["list_files", "read_file", "session_detail", "sessions_overview"]


async def test_delegation_is_opt_in(tmp_path):
    server, plugins, _ = build(settings(tmp_path, ("files", "memory", "delegation")))
    names = await tool_names(server)
    assert {"delegate_task", "task_updates", "pending_tasks", "report_result", "memory_read"} <= set(names)
    assert "delegation" in plugins


async def test_calls_are_logged_with_arguments(tmp_path):
    server, _, log = build(settings(tmp_path, ("files", "memory")))
    result = await server.call_tool("read_file", {"path": "hello.md"})
    assert "hi" in str(result)
    await server.call_tool("memory_remember", {"note": "Demo on  Friday"})
    entries = log.read()
    assert [e["tool"] for e in entries] == ["read_file", "memory_remember"]
    assert entries[0]["path"] == "hello.md"
    assert "Demo on Friday" in (tmp_path / "state" / "memory.md").read_text()


def test_unknown_plugin(tmp_path):
    with pytest.raises(ValueError, match="unknown plugin"):
        build(settings(tmp_path, ("files", "shell")))

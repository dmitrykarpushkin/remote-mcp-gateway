# remote-mcp-gateway

A small **remote MCP server** that gives Claude (claude.ai custom connectors, Claude Code, the Agent SDK)
or any other MCP client safe, audited access to a machine: a shared key, a JSONL log of every tool call,
read-only tools by default, and an opt-in plugin that lets a chat or voice model **delegate work to
background agents** and read the results back later.

It runs in production as the "hands" of a personal assistant: a voice conversation on a phone uses it to
check what the coding agents on a server are doing, read shared notes, and hand off tasks.

## Why

Hosted assistants can only reach your machine through remote MCP connectors, and those connectors have sharp
edges: some clients only send a fixed set of header names, voice modes may not send headers at all, and the
model's own account of what it did is not evidence. This gateway is the minimum that makes that safe enough
to use daily:

- **Key auth as ASGI middleware**: `Authorization: Bearer`, `X-API-Key` or `X-Gateway-Key`, compared in constant
  time; optionally the key as the first path segment for header-less clients (masked in logs). The key is
  generated on first start with mode `600`.
- **Audit log**: every call, with its arguments, goes to `calls.jsonl` before the tool runs.
- **Least privilege**: plugins are opt-in. The defaults (`files`, `sessions`) only read; file access is
  confined to one root (no `..`, absolute paths, dotfiles or symlinks out of the root).
- **Delegation without giving the model a shell**: `delegate_task` only queues text. Executors are separate,
  sandboxed agent sessions that pick tasks up via `pending_tasks` and close them with `report_result`.

## Architecture

```
 MCP client (claude.ai connector, Claude Code, SDK)
        │  streamable HTTP  /mcp   (key in header or /<key>/mcp)
        ▼
 ┌─────────────── RequireKey (ASGI) ───────────────┐
 │  MCPServer                                      │
 │   ├─ logged_tool ─▶ CallLog (calls.jsonl)       │
 │   ├─ files       list_files, read_file          │  read-only, confined to files.root
 │   ├─ sessions    sessions_overview,             │  read-only: Claude Code session registry
 │   │              session_detail                 │  and transcripts, configured projects only
 │   ├─ memory      memory_read, memory_remember   │  append-only notes (opt-in)
 │   └─ delegation  delegate_task, task_updates,   │  opt-in
 │                  pending_tasks, report_result   │
 └───────────────────────┬─────────────────────────┘
                         │ TaskStore (tasks.json, atomic writes) + worker thread
                         ▼
               Dispatcher.fire(task)
               ├─ none            executors poll pending_tasks
               ├─ command         any argv, task text on stdin (webhook, queue, script)
               └─ claude-trigger  fire a saved Claude Code remote trigger via the headless CLI;
                                  the trigger carries a fixed message, tasks wait in the store
```

The `claude-trigger` dispatcher is how a voice conversation wakes a long-running coding agent: a cheap model in
headless `claude -p` gets exactly one allowed tool (`RemoteTrigger`) and one instruction, so the gateway never
touches the user's tokens. A failed fire is retried once and surfaced in `task_updates` with the reason; tasks
queued before a restart are re-dispatched on start.

## Run

```bash
pip install -e .
cp gateway.example.toml gateway.toml     # set files.root, sessions.projects, plugins
GATEWAY_CONFIG=gateway.toml mcp-gateway
# workspace: http://127.0.0.1:8766/mcp, plugins files, sessions, key in .state/key
```

Expose it through a tunnel or reverse proxy with TLS (Cloudflare Tunnel, Tailscale Funnel, nginx), then add it
as a custom connector with the header `Authorization: Bearer <contents of .state/key>`.

Claude Code:

```bash
claude mcp add --transport http workspace https://your-host/mcp --header "Authorization: Bearer $(cat .state/key)"
```

## Example

```text
> what are my coding sessions doing?
  ⎿ sessions_overview()
[website] Fix the footer — waiting for you, active 3 min ago
  you wrote: please fix the footer on mobile
  agent said last: The footer overlaps the cookie banner below 380px. Should I move the banner up?
  unfinished tool calls (may wait for permission): Edit

[api] Rate limits — working, active just now
  you wrote: add per-key rate limits

> ask the website agent to go ahead and move the banner
  ⎿ delegate_task(task="Website session: yes, move the cookie banner above the footer")
Accepted (id t3f9a1c). The result will appear in task_updates.
```

```bash
$ tail -2 .state/calls.jsonl
{"ts": "…", "tool": "sessions_overview"}
{"ts": "…", "tool": "delegate_task", "task": "Website session: yes, move the cookie banner above the footer"}
```

## Development

```bash
pip install -e ".[dev]"
ruff check . && ruff format --check .
pytest -q
```

Tests cover the auth middleware over an in-process ASGI transport, path confinement, transcript parsing on
fixture JSONL, the task lifecycle, retries and restart recovery, and all dispatchers with a mocked
`subprocess.run`; nothing touches the network or a real `claude` binary.

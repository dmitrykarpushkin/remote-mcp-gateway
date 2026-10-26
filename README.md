# remote-mcp-gateway

**English** · [Русский](README.ru.md)

[![CI](https://github.com/dmitrykarpushkin/remote-mcp-gateway/actions/workflows/ci.yml/badge.svg)](https://github.com/dmitrykarpushkin/remote-mcp-gateway/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

**Let Claude on your phone or in the browser reach your machine, with a key, a log of every call and no shell.**

For people who want a hosted assistant (a claude.ai custom connector, voice mode, Claude Code, the Agent SDK) to
check on their server, read their notes and hand work to background agents, without giving the model free rein.

```text
> what are my coding sessions doing?
  ⎿ sessions_overview()
[website] Fix the footer — waiting for you, active 3 min ago
  agent said last: The footer overlaps the cookie banner below 380px. Should I move the banner up?

> ask the website agent to go ahead and move the banner
  ⎿ delegate_task(task="Website session: yes, move the cookie banner above the footer")
Accepted (id t3f9a1c). The result will appear in task_updates.
```

*An illustrative session: the model sees what the coding agents are doing and queues a task, but never runs a command.*

## Why use it

- **Works with clients that cannot set custom headers.** The key is accepted as `Authorization: Bearer`,
  `X-API-Key`, `X-Gateway-Key` or, for header-less clients, as the first path segment (masked in the log).
- **Every call is written down before it runs.** Tool name and arguments go to `calls.jsonl`, so you can check
  what the model did instead of trusting its own account.
- **Read-only unless you say otherwise.** The default tools only read, and file access is confined to one folder:
  no `..`, absolute paths, dotfiles or symlinks out of it.
- **Delegation without a shell.** `delegate_task` only queues text; separate, sandboxed agent sessions pick tasks
  up and report results back.
- **Small and tested.** Built on FastMCP; 39 tests run without network or a real `claude` binary.

## How it compares

| | Local MCP server (stdio) | A stdio server bridged to HTTP behind a tunnel | **remote-mcp-gateway** |
|---|---|---|---|
| Reachable from claude.ai, phone, voice | no | yes | yes |
| Auth that header-less clients can pass | not needed | up to you | built in |
| Log of every call | up to you | up to you | built in, written before the call |
| Hand tasks to background agents | no | no | opt-in plugin |

If the assistant only runs on your laptop, a local stdio server is simpler and safer. Use this gateway when the
client is hosted and you need it to reach a machine of yours over the internet.

## Quick start

```bash
git clone https://github.com/dmitrykarpushkin/remote-mcp-gateway && cd remote-mcp-gateway
pip install -e . && cp gateway.example.toml gateway.toml   # set files.root, sessions.projects, plugins
GATEWAY_CONFIG=gateway.toml mcp-gateway                     # http://127.0.0.1:8766/mcp, key in .state/key
```

Put it behind TLS (Cloudflare Tunnel, Tailscale Funnel or nginx) and add it as a custom connector with
`Authorization: Bearer <contents of .state/key>`. For Claude Code:

```bash
claude mcp add --transport http workspace https://your-host/mcp --header "Authorization: Bearer $(cat .state/key)"
```

## How it works

```text
MCP client --HTTPS--> key check --> FastMCP server --> call log (calls.jsonl)
                                        ├─ files       read-only, one root folder
                                        ├─ sessions    read-only view of Claude Code sessions
                                        ├─ memory      append-only notes (opt-in)
                                        └─ delegation  task queue + dispatcher (opt-in)
```

Plugins, dispatchers (poll, any command, a saved Claude Code remote trigger) and the design choices are in
[docs/design.md](docs/design.md).

## Status

Runs as the "hands" of a personal voice assistant: from a phone it checks what the coding agents on a
server are doing, reads shared notes and hands off tasks. Rewritten onto FastMCP in October 2026.

## Development

```bash
pip install -e ".[dev]"
ruff check . && ruff format --check .
pytest -q
```

---

License: [MIT](LICENSE) · Author: [Dmitry Karpushkin](https://github.com/dmitrykarpushkin)

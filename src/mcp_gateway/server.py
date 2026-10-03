"""Build the MCP server from settings and serve it over streamable HTTP behind the key middleware."""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from .auth import RequireKey, load_key
from .calllog import CallLog
from .config import Settings
from .plugins import register_all


def build(settings: Settings) -> tuple[MCPServer, dict, CallLog]:
    server = MCPServer(name=settings.name, instructions=settings.instructions)
    log = CallLog(settings.calls_log)
    plugins = register_all(server, settings, log)
    return server, plugins, log


def asgi_app(settings: Settings, server: MCPServer):
    app = server.streamable_http_app(
        streamable_http_path="/mcp",
        # Bound to localhost behind a tunnel or reverse proxy: auth is the key, not the Host header.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    return RequireKey(app, load_key(settings.key_file), path_key=settings.path_key)


def main() -> None:
    import uvicorn

    settings = Settings.load()
    server, plugins, _ = build(settings)
    if "delegation" in plugins:
        plugins["delegation"].start()
    print(
        f"{settings.name}: http://{settings.host}:{settings.port}/mcp, plugins {', '.join(settings.plugins)}, "
        f"key in {settings.key_file}",
        flush=True,
    )
    uvicorn.run(
        asgi_app(settings, server),
        host=settings.host,
        port=settings.port,
        log_level="info",
        access_log=False,
        timeout_graceful_shutdown=3,
    )


if __name__ == "__main__":
    main()

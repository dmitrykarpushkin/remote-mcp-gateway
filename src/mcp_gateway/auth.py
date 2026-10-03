"""Shared-key auth for the HTTP transport, as an ASGI middleware."""

from __future__ import annotations

import hmac
import secrets
from pathlib import Path


def load_key(path: Path) -> str:
    """Read the key, creating a random one (mode 600) on first start."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(secrets.token_urlsafe(32))
        path.chmod(0o600)
    return path.read_text().strip()


class RequireKey:
    """Every HTTP request needs the key; anything else gets 401.

    Accepted as `Authorization: Bearer <key>`, `X-API-Key: <key>` or `X-Gateway-Key: <key>`: hosted MCP clients
    often allow only a fixed set of header names for custom connectors. With `path_key=True` the key may also be
    the first URL segment (`/<key>/mcp`) for clients that cannot send headers at all; it is stripped before
    routing and masked in the access log.
    """

    def __init__(self, app, key: str, path_key: bool = False, log=print):
        self.app, self.key, self.path_key, self.log = app, key.encode(), path_key, log

    def _ok(self, headers: dict) -> bool:
        auth = headers.get(b"authorization", b"")
        candidates = [
            auth[7:] if auth.lower().startswith(b"bearer ") else auth,
            headers.get(b"x-api-key", b""),
            headers.get(b"x-gateway-key", b""),
        ]
        return any(c and hmac.compare_digest(c.strip(), self.key) for c in candidates)

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            path = scope.get("path", "")
            prefix = "/" + self.key.decode()
            if self.path_key and path.startswith(prefix + "/"):
                rest = path[len(prefix) :]
                scope = dict(scope, path=rest, raw_path=rest.encode())
                self.log(f"{scope.get('method')} /<key>{rest}")
            elif not self._ok(dict(scope.get("headers") or [])):
                self.log(f"401 {scope.get('method')} {path.replace(prefix, '/<key>')}")
                await send(
                    {"type": "http.response.start", "status": 401, "headers": [(b"content-type", b"text/plain")]}
                )
                await send({"type": "http.response.body", "body": b"unauthorized"})
                return
        await self.app(scope, receive, send)

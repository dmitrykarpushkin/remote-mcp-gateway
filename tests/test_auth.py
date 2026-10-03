import stat

import httpx
import pytest

from mcp_gateway.auth import RequireKey, load_key

KEY = "s3cret-key"


async def echo_app(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"text/plain")]})
    await send({"type": "http.response.body", "body": scope["path"].encode()})


def client(path_key=False, logs=None):
    app = RequireKey(echo_app, KEY, path_key=path_key, log=(logs.append if logs is not None else lambda _: None))
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.mark.parametrize(
    "headers",
    [
        {"Authorization": f"Bearer {KEY}"},
        {"authorization": f"bearer {KEY}"},
        {"X-API-Key": KEY},
        {"X-Gateway-Key": KEY},
    ],
)
async def test_accepts_key_headers(headers):
    async with client() as c:
        r = await c.get("/mcp", headers=headers)
    assert r.status_code == 200 and r.text == "/mcp"


@pytest.mark.parametrize(
    "headers", [{}, {"Authorization": "Bearer wrong"}, {"X-API-Key": ""}, {"Authorization": KEY[:-1]}]
)
async def test_rejects_missing_or_wrong_key(headers):
    async with client() as c:
        r = await c.get("/mcp", headers=headers)
    assert r.status_code == 401


async def test_path_key_is_stripped_and_masked_in_log():
    logs = []
    async with client(path_key=True, logs=logs) as c:
        r = await c.get(f"/{KEY}/mcp")
    assert r.status_code == 200 and r.text == "/mcp"
    assert all(KEY not in line for line in logs)


async def test_path_key_disabled_by_default():
    logs = []
    async with client(logs=logs) as c:
        r = await c.get(f"/{KEY}/mcp")
    assert r.status_code == 401
    assert all(KEY not in line for line in logs)


def test_load_key_creates_private_file_once(tmp_path):
    path = tmp_path / "state" / "key"
    k1 = load_key(path)
    assert len(k1) >= 32
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert load_key(path) == k1

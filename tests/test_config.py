from mcp_gateway.calllog import CallLog
from mcp_gateway.config import Settings


def test_defaults():
    s = Settings.load({})
    assert s.host == "127.0.0.1"
    assert s.plugins == ("files", "sessions")
    assert s.delegation.dispatcher == "none"
    assert s.path_key is False


def test_toml_with_env_overrides(tmp_path):
    cfg = tmp_path / "g.toml"
    cfg.write_text(
        f"""
[gateway]
port = 9001
plugins = ["files", "delegation"]
path_key = true
[files]
root = "{tmp_path}"
[sessions.projects]
"/code/api" = "api"
[delegation]
dispatcher = "command"
command = ["echo"]
"""
    )
    s = Settings.load({"GATEWAY_CONFIG": str(cfg), "GATEWAY_PORT": "9100", "GATEWAY_STATE_DIR": str(tmp_path / "st")})
    assert s.port == 9100
    assert s.plugins == ("files", "delegation")
    assert s.path_key is True
    assert s.files.root == tmp_path.resolve()
    assert s.sessions.projects == {"/code/api": "api"}
    assert s.delegation.command == ["echo"]
    assert s.key_file == tmp_path / "st" / "key"


def test_calllog_truncates_long_values(tmp_path):
    log = CallLog(tmp_path / "c.jsonl", max_value_chars=5)
    log.write("t", note="0123456789", n=3)
    assert log.read()[0] == {**log.read()[0], "tool": "t", "note": "01234", "n": 3}

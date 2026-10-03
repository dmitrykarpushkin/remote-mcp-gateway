import pytest

from mcp_gateway.plugins.memory import Memory


def test_append_only_dated_notes(tmp_path):
    m = Memory(tmp_path / "m.md")
    assert m.text() == ""
    m.remember("Call the dentist\non Monday")
    m.remember("Prefers short answers")
    lines = m.text().splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("- [") and lines[0].endswith("] Call the dentist on Monday")


def test_empty_note_rejected(tmp_path):
    with pytest.raises(ValueError):
        Memory(tmp_path / "m.md").remember("   ")

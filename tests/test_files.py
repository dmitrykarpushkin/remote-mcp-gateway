from mcp_gateway.plugins.files import Files


def make(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text("alpha")
    (tmp_path / "b.txt").write_text("b" * 100)
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("secret")
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "x.log").write_text("noise")
    return Files(tmp_path, hidden=("logs",), max_chars=10, max_entries=50)


def test_list_skips_hidden(tmp_path):
    f = make(tmp_path)
    assert f.list() == ["b.txt", "docs/a.md"]
    assert f.list("docs") == ["docs/a.md"]
    assert f.list("logs") == []
    assert f.list("nope") == []


def test_read_truncates(tmp_path):
    f = make(tmp_path)
    assert f.read("docs/a.md") == "alpha"
    assert f.read("b.txt") == "b" * 10


def test_no_escape_from_root(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    f = make(root)
    outside = tmp_path / "outside.txt"
    outside.write_text("nope")
    for bad in ["../outside.txt", str(outside), "docs/../../outside.txt", ".git/config", "logs/x.log"]:
        assert f.read(bad) == "No such file.", bad
    assert f.list("..") == []


def test_symlink_out_of_root_is_refused(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (tmp_path / "secret.txt").write_text("nope")
    (root / "link.txt").symlink_to(tmp_path / "secret.txt")
    assert Files(root).read("link.txt") == "No such file."

"""Read-only access to one directory tree: list and read text files, never outside the root."""

from __future__ import annotations

from pathlib import Path

from ..calllog import logged_tool


class Files:
    def __init__(self, root: Path, hidden: tuple[str, ...] = (), max_chars: int = 8000, max_entries: int = 200):
        self.root = root.resolve()
        self.hidden = set(hidden)
        self.max_chars = max_chars
        self.max_entries = max_entries

    def _hidden(self, p: Path) -> bool:
        return any(part.startswith(".") or part in self.hidden for part in p.relative_to(self.root).parts)

    def _resolve(self, rel: str) -> Path | None:
        p = (self.root / rel.strip()).resolve()
        if not p.is_relative_to(self.root) or (p != self.root and self._hidden(p)):
            return None
        return p

    def list(self, subdir: str = "") -> list[str]:
        root = self._resolve(subdir)
        if root is None or not root.is_dir():
            return []
        files = (p for p in sorted(root.rglob("*")) if p.is_file() and not self._hidden(p))
        out = []
        for p in files:
            out.append(str(p.relative_to(self.root)))
            if len(out) >= self.max_entries:
                break
        return out

    def read(self, path: str) -> str:
        p = self._resolve(path)
        if p is None or not p.is_file():
            return "No such file."
        return p.read_text(errors="replace")[: self.max_chars]


def register(server, settings, log) -> Files:
    c = settings.files
    files = Files(c.root, c.hidden, c.max_chars, c.max_entries)
    tool = logged_tool(server, log)

    @tool
    def list_files(subdir: str = "") -> list[str]:
        """List files of the shared workspace, optionally inside a subfolder such as 'docs/notes'."""
        return files.list(subdir)

    @tool
    def read_file(path: str) -> str:
        """Read a text file of the shared workspace by relative path (first few thousand characters)."""
        return files.read(path)

    return files

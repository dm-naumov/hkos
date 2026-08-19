"""File-backed SnapshotPersistence port for the MCP server.

The SnapshotPersistence port (hkos.snapshot.snapshot_loader.SnapshotPersistence)
is injected from outside the snapshot layer. This file implementation is the
missing production backend: atomic, append-only, plain JSON.

Layout: <root>/snapshots/<project_id>/{snapshot-NNNNN.json, order.json,
history.json}. Writes are atomic (tmp + os.replace).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


class FileSnapshotPersistence:
    """Atomic, append-only, file-backed snapshot persistence."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root) / "snapshots"

    def _project_dir(self, project: str) -> Path:
        return self._root / project

    @staticmethod
    def _read_json(path: Path) -> Any:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _write_atomic(path: Path, data: Any) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        os.replace(tmp, path)

    def latest(self, project: str) -> dict[str, object] | None:
        versions = self._read_json(self._project_dir(project) / "order.json")
        if not versions:
            return None
        last = versions[-1]
        name = last if isinstance(last, str) else f"snapshot-{last:05d}"
        raw = self._read_json(self._project_dir(project) / f"{name}.json")
        return raw if isinstance(raw, dict) else None

    def version(self, project: str, version: str) -> dict[str, object] | None:
        raw = self._read_json(self._project_dir(project) / f"{version}.json")
        return raw if isinstance(raw, dict) else None

    def save(self, project: str, doc: dict[str, object]) -> str:
        d = self._project_dir(project)
        d.mkdir(parents=True, exist_ok=True)
        versions = self._read_json(d / "order.json") or []
        number = len(versions) + 1
        name = f"snapshot-{number:05d}"
        self._write_atomic(d / f"{name}.json", doc)
        versions.append(number)
        self._write_atomic(d / "order.json", versions)
        return name

    def history(self, project: str) -> list[dict[str, object]]:
        raw = self._read_json(self._project_dir(project) / "history.json") or []
        return raw if isinstance(raw, list) else []

    def append_history(self, project: str, entry: dict[str, object]) -> None:
        d = self._project_dir(project)
        d.mkdir(parents=True, exist_ok=True)
        entries = self._read_json(d / "history.json") or []
        entries.append(entry)
        self._write_atomic(d / "history.json", entries)

#!/usr/bin/env python3
"""HKOS Doctor CLI.

Runs the consistency doctor (HkosDoctor) against a project and prints a
verdict. Self-contained: needs no HKOS data beyond the data root.

Usage:
    python3 scripts/doctor_cli.py --project <id|name> [--root <data-root>]

Exit codes: 0 = PASS, 1 = FAIL, 2 = project not found.

The data root defaults to $HKOS_DATA_ROOT or ./hkos (the standard layout
created by StorageEngine.initialize()). Run from the repository root so the
ConfigLoader finds config/hkos-production.yaml.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


class FileSnapshotPersistence:
    """File-backed SnapshotPersistence port (atomic, append-only).

    Layout: <root>/snapshots/<project_id>/{snapshot-NNNNN.json, order.json,
    history.json}. Writes are atomic (tmp + os.replace).
    """

    def __init__(self, root: Path) -> None:
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
        return self._read_json(self._project_dir(project) / "history.json") or []

    def append_history(self, project: str, entry: dict[str, object]) -> None:
        d = self._project_dir(project)
        d.mkdir(parents=True, exist_ok=True)
        entries = self._read_json(d / "history.json") or []
        entries.append(entry)
        self._write_atomic(d / "history.json", entries)


def main() -> int:
    parser = argparse.ArgumentParser(prog="hkos doctor")
    parser.add_argument("--project", required=True, help="project id or name")
    parser.add_argument(
        "--root",
        default=os.environ.get("HKOS_DATA_ROOT", "./hkos"),
        help="HKOS data root (default: $HKOS_DATA_ROOT or ./hkos)")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    # The repository root IS the hkos package; its parent must be on sys.path.
    pkg_parent = str(repo_root.parent)
    if pkg_parent not in sys.path:
        sys.path.insert(0, pkg_parent)

    from hkos.core.config import ConfigLoader
    from hkos.core.logger import HKOSLogger
    from hkos.core.version import VersionManager
    from hkos.index import IndexCache, IndexEngine, IndexQueryExecutor, IndexStore
    from hkos.integration.hermes.doctor import HkosDoctor
    from hkos.repository.repository_manager import RepositoryManager
    from hkos.snapshot import SnapshotEngine
    from hkos.storage import StorageEngine

    root = Path(args.root).resolve()
    os.chdir(repo_root)  # ConfigLoader resolves YAML relative to cwd
    cfg = ConfigLoader(profile="production")
    cfg.load()
    engine = StorageEngine(root=str(root), config=cfg,
                           logger=HKOSLogger(), version=VersionManager())
    engine.initialize()
    repos = RepositoryManager(engine)
    store = IndexStore(engine)
    cache = IndexCache()
    index = IndexEngine(repos, store, HKOSLogger(), cache=cache)
    qc = IndexQueryExecutor(store, cache=cache)
    snapshots = SnapshotEngine(
        repos, FileSnapshotPersistence(root), HKOSLogger(),
        index_provider=qc.snapshot)
    doctor = HkosDoctor(repos, index, snapshots, store)

    project = next(
        (c for c in repos.projects.list()
         if c.id == args.project or c.name == args.project), None)
    if project is None:
        print(f"project not found: {args.project}")
        return 2
    report = doctor.check(project.id)
    print(report.summary())
    return 0 if report.verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

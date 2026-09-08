"""HKOS CLI (DS-017 ЭТАП 5): управление локальной базой из терминала.

Console script `hkos` + `python -m hkos.cli`. Команды:

- doctor   --project <id|name>   consistency doctor (repo == index == snapshot
                                  + relations FK); exit 0 PASS / 1 FAIL
- status                        version, profile, data root, corpus size
- validate --project <id|name>   IndexEngine.validate; exit 0 valid / 1 invalid

Exit codes: 0 OK, 1 check failed (doctor FAIL / validate invalid),
2 project not found, 3 internal error (e.g. index not built).

Тонкая композиция публичных API; ноль бизнес-логики.
Data root: --root > $HKOS_DATA_ROOT > ./hkos.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any

from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.index import IndexCache, IndexEngine, IndexQueryExecutor, IndexStore
from hkos.integration.hermes.doctor import HkosDoctor
from hkos.repository.repository_manager import RepositoryManager
from hkos.snapshot import SnapshotEngine
from hkos.snapshot.file_persistence import FileSnapshotPersistence
from hkos.storage import StorageEngine

__all__ = ["main"]

_EXIT_OK = 0
_EXIT_FAIL = 1
_EXIT_PROJECT_NOT_FOUND = 2
_EXIT_ERROR = 3


class CliContext:
    """Композиция публичных фасадов HKOS для CLI."""

    def __init__(self, root: str) -> None:
        """Инициализация (StorageEngine.initialize обязателен)."""
        cfg = ConfigLoader(profile="production")
        cfg.load()
        self.engine = StorageEngine(
            root=root, config=cfg, logger=HKOSLogger(),
            version=VersionManager())
        self.engine.initialize()
        self.repos = RepositoryManager(self.engine)
        self.store = IndexStore(self.engine)
        cache = IndexCache()
        self.index = IndexEngine(self.repos, self.store, HKOSLogger(),
                                 cache=cache)
        self.qc = IndexQueryExecutor(self.store, cache=cache)
        self.snapshots = SnapshotEngine(
            self.repos,
            FileSnapshotPersistence(self.engine.root),
            HKOSLogger(),
            index_provider=self.qc.snapshot)
        self.doctor = HkosDoctor(
            self.repos, self.index, self.snapshots, self.store)

    def resolve_project(self, project: str) -> Any | None:
        """Найти проект по id или имени (None — не найден)."""
        for p in self.repos.projects.list():
            if p.id == project or p.name == project:
                return p
        return None


def _build_parser() -> argparse.ArgumentParser:
    """Парсер CLI (--root доступен до и после подкоманды — совместимость
    с legacy-вызовом scripts/doctor_cli.py)."""
    root_parent = argparse.ArgumentParser(add_help=False)
    root_parent.add_argument(
        "--root", default=os.environ.get("HKOS_DATA_ROOT", "./hkos"),
        help="HKOS data root (default: $HKOS_DATA_ROOT or ./hkos)")
    parser = argparse.ArgumentParser(
        prog="hkos",
        description="HKOS — deterministic engineering knowledge base CLI",
        parents=[root_parent])
    sub = parser.add_subparsers(dest="command", required=True)

    p_doctor = sub.add_parser(
        "doctor", parents=[root_parent],
        help="consistency check: repository == index == snapshot")
    p_doctor.add_argument("--project", required=True,
                          help="project id or name")

    sub.add_parser("status", parents=[root_parent],
                   help="server-less status of the data root")

    p_validate = sub.add_parser(
        "validate", parents=[root_parent],
        help="index integrity check for a project")
    p_validate.add_argument("--project", required=True,
                            help="project id or name")
    return parser


def _cmd_status(ctx: CliContext) -> int:
    """Печать статуса data root."""
    projects = ctx.repos.projects.list()
    knowledge_total = sum(
        ctx.repos.knowledge.count(p.id) for p in projects)
    print(f"version:      {VersionManager().version_string}")
    print("profile:      production")
    print(f"data_root:    {ctx.engine.root}")
    print(f"projects:     {len(projects)}")
    print(f"knowledge:    {knowledge_total}")
    return _EXIT_OK


def _cmd_doctor(ctx: CliContext, project: str) -> int:
    """Consistency doctor: repo == index == snapshot (+ relations FK)."""
    resolved = ctx.resolve_project(project)
    if resolved is None:
        print(f"project not found: {project}")
        return _EXIT_PROJECT_NOT_FOUND
    try:
        report = ctx.doctor.check(resolved.id)
    except Exception as exc:  # noqa: BLE001 - CLI boundary: no tracebacks
        print(f"doctor error for project {project}: {exc}")
        return _EXIT_ERROR
    print(report.summary())
    return _EXIT_OK if report.verdict == "PASS" else _EXIT_FAIL


def _cmd_validate(ctx: CliContext, project: str) -> int:
    """Индексная целостность проекта (IndexEngine.validate)."""
    resolved = ctx.resolve_project(project)
    if resolved is None:
        print(f"project not found: {project}")
        return _EXIT_PROJECT_NOT_FOUND
    try:
        result = ctx.index.validate(resolved.id)
    except Exception as exc:  # noqa: BLE001 - CLI boundary: no tracebacks
        print(f"validate error for project {project}: {exc}")
        return _EXIT_ERROR
    if result.valid:
        print(f"index validate: VALID (project {project})")
        return _EXIT_OK
    print(f"index validate: INVALID (project {project})")
    for error in result.errors[:10]:
        print(f"  error: {error}")
    for warning in result.warnings[:10]:
        print(f"  warning: {warning}")
    return _EXIT_FAIL


def main(argv: list[str] | None = None) -> int:
    """Точка входа CLI (console script `hkos` и `python -m hkos.cli`)."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    ctx = CliContext(os.path.abspath(args.root))
    if args.command == "status":
        return _cmd_status(ctx)
    if args.command == "doctor":
        return _cmd_doctor(ctx, args.project)
    if args.command == "validate":
        return _cmd_validate(ctx, args.project)
    parser.error(f"unknown command: {args.command}")
    return _EXIT_ERROR  # unreachable (parser.error exits)


if __name__ == "__main__":
    sys.exit(main())

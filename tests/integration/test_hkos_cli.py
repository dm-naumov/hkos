"""IP-017 ЭТАП 5: дистрибутивный CLI (hkos doctor/status/validate).

Subprocess-тесты `python -m hkos.cli` (env PYTHONPATH=parent repo — как в
test_mcp_server). Exit codes: 0 OK / 1 check failed / 2 project not found /
3 internal error.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.index import IndexCache, IndexEngine, IndexQueryExecutor, IndexStore
from hkos.repository.models import Knowledge
from hkos.repository.repository_manager import RepositoryManager
from hkos.services.librarian import Librarian
from hkos.services.project_manager import ProjectManager
from hkos.snapshot import SnapshotEngine
from hkos.snapshot.file_persistence import FileSnapshotPersistence
from hkos.storage import StorageEngine

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PKG_PARENT = str(_REPO_ROOT.parent)


def run_cli(root: str | Path, *argv: str) -> tuple[int, str]:
    """Запустить python -m hkos.cli; вернуть (exit_code, stdout)."""
    env = {
        **os.environ,
        "PYTHONPATH": _PKG_PARENT,
        "HKOS_LOG_LEVEL": "ERROR",
    }
    proc = subprocess.run(
        [sys.executable, "-m", "hkos.cli", *argv, "--root", str(root)],
        capture_output=True, text=True, env=env, cwd=str(_REPO_ROOT),
        timeout=60,
    )
    return proc.returncode, proc.stdout


def seed_root(root: Path, with_index: bool = True,
              extra_unindexed: bool = False,
              corrupt_keyword: bool = False) -> str:
    """Наполнить data root проектом Seed; вернуть project id.

    with_index: знание проиндексировано + снапшот создан;
    extra_unindexed: дополнительное знание БЕЗ index.update (doctor FAIL);
    corrupt_keyword: битая ссылка в keyword.idx (validate INVALID — валидатор
    проверяет внутреннюю консистентность индекса, не repo-направление).
    """
    cfg = ConfigLoader(profile="production")
    cfg.load()
    engine = StorageEngine(
        root=str(root), config=cfg, logger=HKOSLogger(),
        version=VersionManager())
    engine.initialize()
    repos = RepositoryManager(engine)
    pm = ProjectManager(repos, HKOSLogger())
    pid = pm.create(name="Seed", tags=["cli"]).id
    lib = Librarian(repos, HKOSLogger())
    k1 = lib.register(pid, Knowledge(title="cli fact udp", body="udp"))
    if with_index:
        store = IndexStore(engine)
        cache = IndexCache()
        index = IndexEngine(repos, store, HKOSLogger(), cache=cache)
        index.update(pid, k1.id, "knowledge")
        qc = IndexQueryExecutor(store, cache=cache)
        snapshots = SnapshotEngine(
            repos, FileSnapshotPersistence(root), HKOSLogger(),
            index_provider=qc.snapshot)
        snapshots.create(pid, reason="seed")
        if extra_unindexed:
            lib.register(pid, Knowledge(title="unindexed fact udp", body="udp"))
        if corrupt_keyword:
            doc = engine.read_json(f"projects/{pid}/indexes/keyword.idx")
            doc["data"]["postings"]["zzzbroken"] = [{
                "id": "00000000-0000-0000-0000-000000000000",
                "type": "knowledge", "project": pid,
            }]
            engine.write_json(f"projects/{pid}/indexes/keyword.idx", doc)
    return pid


class TestHkosCli:
    """CLI: status / doctor / validate (exit codes и вывод)."""

    def test_status_empty_root(self, tmp_path: Path) -> None:
        code, out = run_cli(tmp_path, "status")
        assert code == 0
        assert "version:" in out
        assert "projects:     0" in out
        assert "knowledge:    0" in out

    def test_status_seeded(self, tmp_path: Path) -> None:
        seed_root(tmp_path)
        code, out = run_cli(tmp_path, "status")
        assert code == 0
        assert "projects:     1" in out
        assert "knowledge:    1" in out

    def test_doctor_pass(self, tmp_path: Path) -> None:
        seed_root(tmp_path)
        code, out = run_cli(tmp_path, "doctor", "--project", "Seed")
        assert code == 0, out
        assert "PASS" in out
        assert "relations FK: dangling links" in out

    def test_doctor_fail(self, tmp_path: Path) -> None:
        seed_root(tmp_path, extra_unindexed=True)
        code, out = run_cli(tmp_path, "doctor", "--project", "Seed")
        assert code == 1
        assert "FAIL" in out
        assert "knowledge consistency" in out

    def test_doctor_project_not_found(self, tmp_path: Path) -> None:
        code, out = run_cli(tmp_path, "doctor", "--project", "Nope")
        assert code == 2
        assert "project not found" in out

    def test_doctor_no_index_is_graceful_error(self, tmp_path: Path) -> None:
        # проект без индекса: doctor.check не может прочитать statistics
        seed_root(tmp_path, with_index=False)
        code, out = run_cli(tmp_path, "doctor", "--project", "Seed")
        assert code == 3, out
        assert "doctor error" in out
        assert "Traceback" not in out

    def test_validate_valid(self, tmp_path: Path) -> None:
        seed_root(tmp_path)
        code, out = run_cli(tmp_path, "validate", "--project", "Seed")
        assert code == 0, out
        assert "VALID" in out

    def test_validate_invalid(self, tmp_path: Path) -> None:
        # битая ссылка в keyword.idx (внутренняя консистентность индекса)
        seed_root(tmp_path, corrupt_keyword=True)
        code, out = run_cli(tmp_path, "validate", "--project", "Seed")
        assert code == 1, out
        assert "INVALID" in out
        assert "broken link" in out

    def test_no_command_usage_error(self, tmp_path: Path) -> None:
        code, _ = run_cli(tmp_path)
        assert code != 0

    def test_legacy_doctor_cli_wrapper(self, tmp_path: Path) -> None:
        """scripts/doctor_cli.py — тонкий враппер (та же команда doctor)."""
        seed_root(tmp_path)
        env = {**os.environ, "PYTHONPATH": _PKG_PARENT,
               "HKOS_LOG_LEVEL": "ERROR"}
        proc = subprocess.run(
            [sys.executable, "scripts/doctor_cli.py",
             "--project", "Seed", "--root", str(tmp_path)],
            capture_output=True, text=True, env=env, cwd=str(_REPO_ROOT),
            timeout=60,
        )
        assert proc.returncode == 0, proc.stdout
        assert "PASS" in proc.stdout

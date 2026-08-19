"""Unit tests: RollbackManager (DS-011 §10, IP-011 ЭТАП 3)."""

import inspect
from pathlib import Path

import pytest

from hkos.migration.exceptions import RollbackError
from hkos.migration.rollback_manager import RollbackManager


def _seed(root: Path, backup_key: str = "001_initial_2") -> Path:
    """Создать Repository с производными + backup ТОЛЬКО Repository."""
    projects = root / "projects"
    p1 = projects / "proj-1"
    (p1 / "knowledge").mkdir(parents=True)
    (p1 / "knowledge" / "k1.json").write_text('{"title": "original"}')
    (p1 / "indexes").mkdir()
    (p1 / "indexes" / "kw.idx").write_text("{}")
    (p1 / "snapshots").mkdir()
    (p1 / "snapshots" / "snap-1.json").write_text("{}")
    # backup (как создаёт BackupManager: только knowledge)
    backup = root / "backup" / backup_key / "projects" / "proj-1"
    (backup / "knowledge").mkdir(parents=True)
    (backup / "knowledge" / "k1.json").write_text('{"title": "original"}')
    return root / "backup" / backup_key


class TestRollbackManager:
    """Restore Repository; delete index/snapshot; без IndexEngine/SnapshotEngine."""

    def test_restore_repository(self, tmp_path: Path) -> None:
        backup_dir = _seed(tmp_path)
        # повреждение Repository
        (tmp_path / "projects" / "proj-1" / "knowledge" / "k1.json").write_text("{}")
        (tmp_path / "projects" / "proj-1" / "knowledge" / "extra.json").write_text("{}")
        result = RollbackManager(tmp_path).rollback(str(backup_dir))
        content = (tmp_path / "projects" / "proj-1" / "knowledge" / "k1.json").read_text()
        assert content == '{"title": "original"}'
        assert not (tmp_path / "projects" / "proj-1" / "knowledge" / "extra.json").exists()
        assert result["restored_projects"] == ["proj-1"]

    def test_rollback_deletes_index(self, tmp_path: Path) -> None:
        backup_dir = _seed(tmp_path)
        RollbackManager(tmp_path).rollback(str(backup_dir))
        assert not (tmp_path / "projects" / "proj-1" / "indexes").exists()

    def test_rollback_deletes_snapshot(self, tmp_path: Path) -> None:
        backup_dir = _seed(tmp_path)
        RollbackManager(tmp_path).rollback(str(backup_dir))
        assert not (tmp_path / "projects" / "proj-1" / "snapshots").exists()

    def test_rollback_repeated_noop(self, tmp_path: Path) -> None:
        """Повторный rollback на тот же backup -> no-op (идентичное состояние)."""
        backup_dir = _seed(tmp_path)
        manager = RollbackManager(tmp_path)
        manager.rollback(str(backup_dir))  # первый — выполняется
        second = manager.rollback(str(backup_dir))  # повторный — no-op
        content = (tmp_path / "projects" / "proj-1" / "knowledge" / "k1.json").read_text()
        assert content == '{"title": "original"}'
        assert second["restored_projects"] == ["proj-1"]
        assert second["deleted_indexes"] == []  # уже удалены — no-op

    def test_rollback_after_partial_deletion(self, tmp_path: Path) -> None:
        """Прерванный restore: повторная попытка завершает восстановление."""
        backup_dir = _seed(tmp_path)
        # частичное повреждение: каталог знаний удалён полностью
        import shutil
        shutil.rmtree(tmp_path / "projects" / "proj-1" / "knowledge")
        result = RollbackManager(tmp_path).rollback(str(backup_dir))
        assert (tmp_path / "projects" / "proj-1" / "knowledge" / "k1.json").exists()
        assert result["restored_projects"] == ["proj-1"]

    def test_rollback_no_indexengine(self) -> None:
        """RollbackManager НЕ зависит от IndexEngine (нет импортов)."""
        source = inspect.getsource(RollbackManager)
        for line in source.splitlines():
            if line.startswith(("from hkos.index", "import hkos.index",
                                "from hkos.snapshot", "import hkos.snapshot",
                                "IndexEngine", "SnapshotEngine")):
                assert False, f"зависимость от производных: {line.strip()}"

    def test_rollback_missing_backup_raises(self, tmp_path: Path) -> None:
        manager = RollbackManager(tmp_path)
        with pytest.raises(RollbackError):
            manager.rollback(str(tmp_path / "backup" / "nope"))

    def test_rollback_returns_info(self, tmp_path: Path) -> None:
        backup_dir = _seed(tmp_path)
        result = RollbackManager(tmp_path).rollback(str(backup_dir))
        assert set(result.keys()) == {
            "backup_dir", "restored_projects", "deleted_indexes", "deleted_snapshots",
        }

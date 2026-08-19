"""Unit tests: BackupManager (DS-011 §9, IP-011 ЭТАП 3)."""

from pathlib import Path

import pytest

from hkos.migration.backup_manager import BackupManager
from hkos.migration.exceptions import BackupError


class TestBackupManager:
    """Копия ТОЛЬКО Repository; ключ (migration_id, target); reuse; keep-N."""

    @staticmethod
    def _seed_repository(root: Path) -> None:
        projects = root / "projects"
        p1 = projects / "proj-1"
        (p1 / "knowledge").mkdir(parents=True)
        (p1 / "knowledge" / "k1.json").write_text('{"version": 1}')
        (p1 / "knowledge" / "k2.json").write_text('{"version": 1}')
        # производные ВНУТРИ проекта: должны быть ИСКЛЮЧЕНЫ из backup
        (p1 / "indexes").mkdir()
        (p1 / "indexes" / "kw.idx").write_text("{}")
        (p1 / "snapshots").mkdir()
        (p1 / "snapshots" / "snapshot-1.json").write_text("{}")
        (p1 / "project.json").write_text('{"name": "p1"}')
        p2 = projects / "proj-2"
        (p2 / "knowledge").mkdir(parents=True)
        (p2 / "knowledge" / "k3.json").write_text('{"version": 1}')
        (p2 / "indexes").mkdir()
        (p2 / "indexes" / "kw.idx").write_text("{}")

    def test_backup_created(self, tmp_path: Path) -> None:
        self._seed_repository(tmp_path)
        manager = BackupManager(tmp_path, keep_n=3)
        backup_dir = manager.create("001_initial", 2)
        path = Path(backup_dir)
        assert path.is_dir()
        assert (path / "projects" / "proj-1" / "knowledge" / "k1.json").exists()
        assert (path / "projects" / "proj-2" / "knowledge" / "k3.json").exists()

    def test_backup_excludes_indexes_and_snapshots(self, tmp_path: Path) -> None:
        """ТОЛЬКО Repository: никаких index/, никаких snapshot/."""
        self._seed_repository(tmp_path)
        manager = BackupManager(tmp_path, keep_n=3)
        backup_dir = Path(manager.create("001_initial", 2))
        assert not (backup_dir / "projects" / "proj-1" / "indexes").exists()
        assert not (backup_dir / "projects" / "proj-1" / "snapshots").exists()
        assert not (backup_dir / "projects" / "proj-2" / "indexes").exists()
        assert (backup_dir / "projects" / "proj-1" / "knowledge" / "k1.json").exists()

    def test_backup_reuse(self, tmp_path: Path) -> None:
        """Повторный backup с тем же ключом -> reuse (без новой копии)."""
        self._seed_repository(tmp_path)
        manager = BackupManager(tmp_path, keep_n=3)
        first = manager.create("001_initial", 2)
        # изменить источник — reuse не должен копировать заново
        (tmp_path / "projects" / "proj-1" / "knowledge" / "k_new.json").write_text("{}")
        second = manager.create("001_initial", 2)
        assert first == second
        assert not (Path(first) / "projects" / "proj-1" / "knowledge" / "k_new.json").exists()

    def test_backup_immutable(self, tmp_path: Path) -> None:
        """Backup иммутабелен: содержимое не изменяется после создания."""
        self._seed_repository(tmp_path)
        manager = BackupManager(tmp_path, keep_n=3)
        backup_dir = Path(manager.create("001_initial", 2))
        content_before = sorted(
            str(p.relative_to(backup_dir)) for p in backup_dir.rglob("*") if p.is_file()
        )
        # повторные операции не изменяют содержимое
        manager.create("001_initial", 2)
        manager.exists("001_initial", 2)
        content_after = sorted(
            str(p.relative_to(backup_dir)) for p in backup_dir.rglob("*") if p.is_file()
        )
        assert content_before == content_after

    def test_keep_n_rotation(self, tmp_path: Path) -> None:
        """keep-N: старейшие backup удаляются, новые остаются."""
        self._seed_repository(tmp_path)
        manager = BackupManager(tmp_path, keep_n=2)
        b1 = Path(manager.create("001_initial", 2))
        b2 = Path(manager.create("002_next", 3))
        b3 = Path(manager.create("003_final", 4))
        assert b3.is_dir()
        assert b2.is_dir()
        assert not b1.is_dir()  # старейший удалён (keep-N=2)

    def test_keep_n_no_prune_within_limit(self, tmp_path: Path) -> None:
        self._seed_repository(tmp_path)
        manager = BackupManager(tmp_path, keep_n=5)
        b1 = Path(manager.create("001_initial", 2))
        b2 = Path(manager.create("002_next", 3))
        assert b1.is_dir() and b2.is_dir()

    def test_exists_by_key(self, tmp_path: Path) -> None:
        self._seed_repository(tmp_path)
        manager = BackupManager(tmp_path, keep_n=3)
        assert manager.exists("001_initial", 2) is False
        manager.create("001_initial", 2)
        assert manager.exists("001_initial", 2) is True
        assert manager.exists("001_initial", 3) is False

    def test_missing_repository_raises(self, tmp_path: Path) -> None:
        manager = BackupManager(tmp_path, keep_n=3)
        with pytest.raises(BackupError):
            manager.create("001_initial", 2)

    def test_keep_n_invalid(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError):
            BackupManager(tmp_path, keep_n=0)

    def test_backup_dir_name_encodes_key(self, tmp_path: Path) -> None:
        self._seed_repository(tmp_path)
        manager = BackupManager(tmp_path, keep_n=3)
        backup_dir = Path(manager.create("001_initial", 2))
        assert backup_dir.name == "001_initial_2"
        assert backup_dir.parent.name == "backup"

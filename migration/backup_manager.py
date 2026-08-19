"""HKOS Backup Manager (DS-011 Rev.1.2 §9, IP-011 ЭТАП 3)
=============================================================
Резервные копии Repository (projects/) — ЕДИНСТВЕННЫЙ источник истины.

Правила:
- backup содержит ТОЛЬКО Repository: каталоги indexes/ и snapshots/
  (внутри проектов) ИСКЛЮЧАЮТСЯ из копии (производные, перестраиваемы);
- ключ backup: (migration_id, target_version); имя каталога:
  backup/<migration_id>_<target_version>/;
- повторный backup с тем же ключом -> ПЕРЕИСПОЛЬЗОВАНИЕ (без новой копии);
- backup ИММУТАБЕЛЕН: нет API записи/изменения содержимого;
- единственное удаление — keep-N ротация (старые копии);
- все пути через pathlib; создание копии атомарно (tmp + rename);
- без глобальных переменных.
"""

import os
import shutil
from pathlib import Path

from hkos.migration.exceptions import BackupError
from hkos.storage.path_manager import PathManager

__all__ = ["BackupManager"]


class BackupManager:
    """Создание/переиспользование/ротация резервных копий (DS-011 §9)."""

    def __init__(self, root: Path, keep_n: int = 5) -> None:
        """Инициализация.

        Args:
            root: Корень рабочей области (workspace).
            keep_n: Сколько последних backup хранить (ротация).

        Raises:
            ValueError: keep_n < 1.

        """
        if keep_n < 1:
            raise ValueError(f"keep_n must be >= 1, got {keep_n}")
        self._root = Path(root)
        self._backup_root = self._root / "backup"
        self._projects_root = self._root / PathManager.ROOT_PROJECTS
        self._keep_n = keep_n

    def create(self, migration_id: str, target_version: int) -> str:
        """Создать backup по ключу (migration_id, target_version).

        Если backup с тем же ключом уже существует — ПЕРЕИСПОЛЬЗУЕТСЯ
        (новая копия не создаётся; DS-011 §9).

        Returns:
            Путь к каталогу backup.

        Raises:
            BackupError: корень Repository отсутствует.

        """
        key_dir = self._backup_dir(migration_id, target_version)
        if key_dir.exists():
            return str(key_dir)  # reuse
        if not self._projects_root.is_dir():
            raise BackupError(
                f"Repository root not found: {self._projects_root}"
            )
        tmp = self._backup_root / f".tmp_{migration_id}_{target_version}"
        shutil.rmtree(tmp, ignore_errors=True)
        try:
            self._backup_root.mkdir(parents=True, exist_ok=True)
            # Структура: backup/<key>/projects/ (ТОЛЬКО Repository;
            # indexes/snapshots исключаются)
            tmp_projects = tmp / PathManager.ROOT_PROJECTS
            shutil.copytree(
                self._projects_root,
                tmp_projects,
                ignore=shutil.ignore_patterns(
                    PathManager.PROJECT_INDEXES, PathManager.PROJECT_SNAPSHOTS,
                ),
            )
            os.replace(tmp, key_dir)  # атомарный rename
        except OSError as exc:
            shutil.rmtree(tmp, ignore_errors=True)
            raise BackupError(
                f"Backup failed for {migration_id} -> {target_version}: {exc}"
            ) from exc
        self._prune()
        return str(key_dir)

    def restore(self, backup_dir: str) -> None:
        """Восстановить Repository из backup (backup не изменяется)."""
        raise NotImplementedError("ЭТАП 4: восстановление через RollbackManager")

    def exists(self, migration_id: str, target_version: int) -> bool:
        """Существует ли backup по ключу."""
        return self._backup_dir(migration_id, target_version).is_dir()

    def _backup_dir(self, migration_id: str, target_version: int) -> Path:
        """Каталог backup по ключу: backup/<migration_id>_<target_version>/."""
        return self._backup_root / f"{migration_id}_{target_version}"

    def _prune(self) -> None:
        """Keep-N: удалить старейшие backup сверх лимита (единственное
        удаление, разрешённое BackupManager; DS-011 §9).
        """
        candidates = [
            entry for entry in self._backup_root.iterdir()
            if entry.is_dir() and not entry.name.startswith(".tmp_")
        ]
        if len(candidates) <= self._keep_n:
            return
        ordered = sorted(candidates, key=lambda p: p.stat().st_mtime)
        for stale in ordered[: len(ordered) - self._keep_n]:
            shutil.rmtree(stale, ignore_errors=True)

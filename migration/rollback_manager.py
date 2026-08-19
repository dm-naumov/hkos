"""HKOS Rollback Manager (DS-011 Rev.1.2 §10, IP-011 ЭТАП 3)
=============================================================
Откат миграции — ТОЛЬКО физическое восстановление:

1. Восстановить Repository из backup (иммутабельного);
2. УДАЛИТЬ существующий index (НЕ восстанавливать — запрет stale-индексов);
3. УДАЛИТЬ существующий snapshot (НЕ восстанавливать);
4. Вернуть информацию о выполненных действиях.

RollbackManager НЕ знает про IndexEngine/SnapshotEngine: rebuild и
regenerate НЕ выполняются (вне ответственности; DS-011 §10).

Идемпотентность:
- повторный rollback на тот же backup -> no-op (состояние идентично);
- прерванный rollback -> повторная попытка завершает восстановление
  (копирование по-каталогам с перезаписью).
"""

import shutil
from pathlib import Path

from hkos.migration.exceptions import RollbackError
from hkos.storage.path_manager import PathManager

__all__ = ["RollbackManager"]


class RollbackManager:
    """Физический откат: restore Repository + удаление производных."""

    def __init__(self, root: Path) -> None:
        """Инициализация.

        Args:
            root: Корень рабочей области (workspace).

        """
        self._root = Path(root)
        self._projects_root = self._root / PathManager.ROOT_PROJECTS

    def rollback(self, backup_dir: str) -> dict[str, object]:
        """Откат: restore Repository; delete index; delete snapshot.

        Args:
            backup_dir: Каталог backup (результат BackupManager.create).

        Returns:
            Информация: restored_projects, deleted_indexes,
            deleted_snapshots, backup_dir. Rebuild НЕ выполняется.

        Raises:
            RollbackError: backup отсутствует.

        """
        backup_path = Path(backup_dir)
        backup_projects = backup_path / PathManager.ROOT_PROJECTS
        if not backup_projects.is_dir():
            raise RollbackError(f"Backup not found: {backup_dir}")
        restored = self._restore_repository(backup_projects)
        deleted_indexes = self._delete_indexes()
        deleted_snapshots = self._delete_snapshots()
        return {
            "backup_dir": str(backup_path),
            "restored_projects": restored,
            "deleted_indexes": deleted_indexes,
            "deleted_snapshots": deleted_snapshots,
        }

    def _restore_repository(self, backup_projects: Path) -> list[str]:
        """Приведение Repository к состоянию backup (идемпотентно:
        повторный restore того же backup даёт идентичное состояние;
        прерванный restore завершается повторной попыткой).

        Проекты, добавленные ПОСЛЕ backup, удаляются (Repository обязан
        совпасть с backup; DS-011 §10 «восстановить резервную копию»).
        """
        self._projects_root.mkdir(parents=True, exist_ok=True)
        backup_names = {
            entry.name for entry in backup_projects.iterdir()
            if entry.is_dir()
        }
        for live in sorted(self._projects_root.iterdir()):
            if live.is_dir() and live.name not in backup_names:
                shutil.rmtree(live)  # создан после backup — удаляется
        restored: list[str] = []
        for project_dir in sorted(backup_projects.iterdir()):
            if not project_dir.is_dir():
                continue
            target = self._projects_root / project_dir.name
            # Равенство с backup: удалить живой проект и скопировать из
            # backup (файлы, добавленные после backup, исчезают).
            # Восстанавливаемо: прерванный шаг завершается повторной
            # попыткой (rmtree + copytree идемпотентны по-проекту).
            shutil.rmtree(target, ignore_errors=True)
            shutil.copytree(project_dir, target)
            restored.append(project_dir.name)
        return restored

    def _delete_indexes(self) -> list[str]:
        """Удалить существующие каталоги индексов (НЕ восстанавливать)."""
        deleted: list[str] = []
        for project_dir in sorted(self._projects_root.iterdir()):
            if not project_dir.is_dir():
                continue
            index_dir = project_dir / PathManager.PROJECT_INDEXES
            if index_dir.is_dir():
                shutil.rmtree(index_dir)
                deleted.append(project_dir.name)
        return deleted

    def _delete_snapshots(self) -> list[str]:
        """Удалить существующие каталоги снимков (НЕ восстанавливать)."""
        deleted: list[str] = []
        for project_dir in sorted(self._projects_root.iterdir()):
            if not project_dir.is_dir():
                continue
            snapshot_dir = project_dir / PathManager.PROJECT_SNAPSHOTS
            if snapshot_dir.is_dir():
                shutil.rmtree(snapshot_dir)
                deleted.append(project_dir.name)
        return deleted

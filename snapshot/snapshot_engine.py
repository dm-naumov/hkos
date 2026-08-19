"""HKOS Snapshot Engine (DS-010 §6, IP-010)
==========================================
Публичный фасад Snapshot Layer.

Публичный API (ровно эти методы):
    create, load, update, diff, validate, serialize, statistics, history

Правила (IP-010):
- использует RepositoryManager и СУЩЕСТВУЮЩИЙ SnapshotLoader (context);
- прямой доступ к Storage запрещён (персистентность — порт, инжектируется);
- Retrieval Engine не используется;
- Snapshot — независимый агрегат, append-only.
"""

from typing import Any, Callable

from hkos.core.logger import HKOSLogger
from hkos.index.query_contract import IndexSnapshot
from hkos.kernel.snapshot_document import SnapshotDocument
from hkos.repository.repository_manager import RepositoryManager
from hkos.snapshot.snapshot_loader import SnapshotPersistence
from hkos.snapshot.snapshot_manager import SnapshotManager

__all__ = ["SnapshotEngine"]


class SnapshotEngine:
    """Публичный фасад Snapshot Engine (8 методов)."""

    def __init__(
        self,
        repositories: RepositoryManager,
        persistence: SnapshotPersistence,
        logger: HKOSLogger,
        index_provider: Callable[[str], IndexSnapshot | None] | None = None,
        manager: SnapshotManager | None = None,
    ) -> None:
        """Инициализация Snapshot Engine.

        Args:
            repositories: RepositoryManager (Builder/Validator).
            persistence: Порт персистентности (append-only, вне слоя).
            logger: HKOSLogger.
            index_provider: Провайдер Entity Index снимка (Q3) для
                классификации; None — без классификации.
            manager: SnapshotManager; создаётся по умолчанию.

        """
        self._repositories = repositories
        self._persistence = persistence
        self._logger = logger
        self._manager = manager if manager is not None else SnapshotManager(
            repositories, persistence, index_provider
        )

    # --- Публичный API ---

    def create(
        self,
        project: str,
        campaign_id: str = "",
        author: str = "",
        reason: str = "manual",
        comment: str = "",
        branch: str = "main",
        force: bool = False,
    ) -> SnapshotDocument:
        """Создать Snapshot (append-only; правило DS-010 §10).

        Args:
            project: UUID проекта.
            campaign_id: UUID кампании.
            author: Автор.
            reason: Причина создания.
            comment: Комментарий.
            branch: Ветка.
            force: Принудительное создание.

        Returns:
            SnapshotDocument (созданный или последний при отсутствии
            изменений канонического состояния).

        """
        self._logger.info("Snapshot Created")
        return self._manager.create(
            project, campaign_id, author, reason, comment, branch, force
        )

    def load(
        self, project: str, version: str | None = None
    ) -> SnapshotDocument | None:
        """Загрузить Snapshot: последний или указанной версии.

        Args:
            project: UUID проекта.
            version: Версия (например, "00041") или None — последняя.

        Returns:
            SnapshotDocument или None.

        """
        self._logger.info("Snapshot Loaded")
        return self._manager.load(project, version)

    def update(
        self,
        project: str,
        campaign_id: str = "",
        author: str = "",
        reason: str = "manual",
        comment: str = "",
        branch: str = "main",
    ) -> SnapshotDocument:
        """Обновить Snapshot (DS-010 §10): создаёт новую версию ТОЛЬКО
        при изменении канонического состояния; иначе — последний снимок.

        Args:
            project: UUID проекта.
            campaign_id: UUID кампании.
            author: Автор.
            reason: Причина обновления.
            comment: Комментарий.
            branch: Ветка.

        Returns:
            SnapshotDocument.

        """
        self._logger.info("Snapshot Updated")
        return self._manager.create(
            project, campaign_id, author, reason, comment, branch, force=False
        )

    def diff(
        self, snapshot_a: SnapshotDocument, snapshot_b: SnapshotDocument
    ) -> Any:
        """Сравнить два Snapshot (только документы, без Repository).

        Args:
            snapshot_a: Базовый снимок.
            snapshot_b: Новый снимок.

        Returns:
            DiffResult (added/removed/modified/unchanged).

        """
        self._logger.info("Snapshot Compared")
        return self._manager.diff(snapshot_a, snapshot_b)

    def validate(self, snapshot: SnapshotDocument) -> Any:
        """Проверить Snapshot (битые ссылки/UUID/структура/Repository)."""
        self._logger.info("Snapshot Validated")
        return self._manager.validate(snapshot)

    def serialize(self, snapshot: SnapshotDocument) -> dict[str, object]:
        """Сериализовать Snapshot (стабильный конверт HKOS-08)."""
        return self._manager.serialize(snapshot)

    def statistics(self, project: str) -> dict[str, object]:
        """Статистика Snapshot проекта."""
        return self._manager.statistics(project)

    def history(self, project: str) -> list[dict[str, str]]:
        """История Snapshot (append-only)."""
        return self._manager.history(project)

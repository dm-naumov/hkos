"""HKOS Snapshot Manager (DS-010, IP-010)
==========================================
Оркестрация Snapshot Engine: создание (с правилом обновления DS-010 §10),
загрузка, diff, валидация, история. Версии нумеруются последовательно
(snapshot-NNNNN, HKOS-10 §5); удаление/изменение старых Snapshot запрещены
(append-only).
"""

from datetime import datetime, timezone
from typing import Any, Callable

from hkos.index.query_contract import IndexSnapshot
from hkos.kernel.snapshot_document import SnapshotDocument
from hkos.repository.repository_manager import RepositoryManager
from hkos.snapshot.snapshot_builder import SnapshotBuilder
from hkos.snapshot.snapshot_diff import SnapshotDiff
from hkos.snapshot.snapshot_history import SnapshotHistory
from hkos.snapshot.snapshot_loader import SnapshotLoader, SnapshotPersistence
from hkos.snapshot.snapshot_serializer import SnapshotSerializer
from hkos.snapshot.snapshot_validator import SnapshotValidator

__all__ = ["SnapshotManager"]


def _now() -> str:
    """Текущее время ISO-8601 (UTC)."""
    return datetime.now(timezone.utc).isoformat()


class SnapshotManager:
    """Оркестрация Snapshot Engine (создание/загрузка/diff/валидация/история)."""

    def __init__(
        self,
        repositories: RepositoryManager,
        persistence: SnapshotPersistence,
        snapshot_index_provider: Callable[[str], IndexSnapshot | None] | None = None,
    ) -> None:
        """Инициализация менеджера.

        Args:
            repositories: RepositoryManager (Builder/Validator).
            persistence: Порт персистентности (append-only).
            snapshot_index_provider: Провайдер снимка Entity Index (Q3)
                для классификации; None — без классификации.

        """
        self._repositories = repositories
        self._persistence = persistence
        self._index_provider = snapshot_index_provider
        self._builder = SnapshotBuilder(repositories)
        self._diff = SnapshotDiff()
        self._history = SnapshotHistory(persistence)
        self._loader = SnapshotLoader(persistence)
        self._serializer = SnapshotSerializer()
        self._validator = SnapshotValidator(repositories)

    # --- Внутренние ---

    def _next_snapshot_id(self, project: str) -> tuple[str, str]:
        """Следующий snapshot_id и предыдущая версия."""
        latest = self._persistence.latest(project)
        previous_version = ""
        number = 1
        if isinstance(latest, dict):
            snapshot_id = str(latest.get("snapshot_id", ""))
            if snapshot_id:
                previous_version = snapshot_id
                digits = "".join(ch for ch in snapshot_id if ch.isdigit())
                if digits:
                    number = int(digits) + 1
        return f"snapshot-{number:05d}", previous_version

    def _new_document(
        self,
        project: str,
        campaign_id: str,
        author: str,
        reason: str,
        comment: str,
        branch: str,
        snapshot_id: str,
        previous_version: str,
    ) -> SnapshotDocument:
        """Новый документ Snapshot (метаданные + время)."""
        return SnapshotDocument(
            snapshot_id=snapshot_id,
            timestamp=_now(),
            project_id=project,
            campaign_id=campaign_id,
            parent=previous_version,
            branch=branch,
            author=author,
            comment=comment,
            knowledge_version="graph-current",
            index_version="index-current",
            canonical_version="canon-current",
            hash="",
        )

    # --- Операции ---

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
        """Создать Snapshot (append-only).

        Правило обновления (DS-010 §10): если каноническое состояние не
        изменилось, новый Snapshot НЕ создаётся (возвращается последний),
        если только force=True.

        Args:
            project: UUID проекта.
            campaign_id: UUID кампании.
            author: Автор.
            reason: Причина создания.
            comment: Комментарий.
            branch: Ветка (HKOS-10 §9).
            force: Принудительное создание (игнорирует правило §10).

        Returns:
            SnapshotDocument (созданный или последний существующий).

        """
        snapshot_id, previous_version = self._next_snapshot_id(project)
        document = self._new_document(
            project, campaign_id, author, reason, comment, branch,
            snapshot_id, previous_version,
        )
        index_snapshot = (
            self._index_provider(project) if self._index_provider else None
        )
        document = self._builder.build(project, document, index_snapshot)

        if not force:
            latest = self._loader.load_latest(project)
            if latest is not None:
                diff = self._diff.diff(latest, document)
                if diff.changed_count == 0:
                    # Каноническое состояние не изменилось (DS-010 §10)
                    return latest

        self._persistence.save(project, self._serializer.serialize(document))
        self._history.append(
            project, snapshot_id, author, campaign_id, reason, comment,
            previous_version,
        )
        return document

    def load(
        self,
        project: str,
        version: str | None = None,
    ) -> SnapshotDocument | None:
        """Загрузить Snapshot: последний или указанной версии.

        Args:
            project: UUID проекта.
            version: Версия (например, "00041") или None — последняя.

        Returns:
            SnapshotDocument или None (снимков нет).

        """
        if version:
            return self._loader.load_version(project, version)
        return self._loader.load_latest(project)

    def diff(
        self, snapshot_a: SnapshotDocument, snapshot_b: SnapshotDocument
    ) -> Any:
        """Сравнить два Snapshot (только документы)."""
        return self._diff.diff(snapshot_a, snapshot_b)

    def validate(self, snapshot: SnapshotDocument) -> Any:
        """Проверить Snapshot (ссылки/UUID/структура/Repository)."""
        return self._validator.validate(snapshot)

    def serialize(self, snapshot: SnapshotDocument) -> dict[str, object]:
        """Сериализовать Snapshot (конверт HKOS-08)."""
        return self._serializer.serialize(snapshot)

    def statistics(self, project: str) -> dict[str, object]:
        """Статистика Snapshot проекта."""
        latest = self._loader.load_latest(project)
        if latest is None:
            return {"project": project, "snapshots": 0}
        history = self._history.entries(project)
        return {
            "project": project,
            "snapshots": len(history),
            "latest_snapshot_id": latest.snapshot_id,
            "latest_timestamp": latest.timestamp,
            "statistics": dict(latest.statistics),
        }

    def history(self, project: str) -> list[dict[str, str]]:
        """История Snapshot (append-only)."""
        return self._history.entries(project)

    @property
    def loader(self) -> SnapshotLoader:
        """Загрузчик (latest/version)."""
        return self._loader

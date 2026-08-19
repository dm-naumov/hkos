"""HKOS Snapshot Loader (DS-010 §14, IP-010)
==========================================
SnapshotLoader (Snapshot Layer) выбирает:
- последний стабильный Snapshot;
- Snapshot указанной версии.

Разбор документа — через ЕДИНЫЙ тип SnapshotDocument (hkos.kernel,
Post-Audit Refinement: документ вынесен из Context Layer; Snapshot Layer
не зависит от Context). Реализация разбора не дублируется — from_dict
определён один раз в kernel.

Персистентность Snapshot (read/write) инжектируется портом
SnapshotPersistence (реализация — вне Snapshot Layer; прямой доступ
к Storage запрещён IP-010).
"""

from typing import Protocol, runtime_checkable

from hkos.kernel.snapshot_document import SnapshotDocument
from hkos.snapshot.exceptions import SnapshotNotFoundError

__all__ = [
    "SnapshotPersistence",
    "SnapshotLoader",
]


@runtime_checkable
class SnapshotPersistence(Protocol):
    """Порт персистентности Snapshot (append-only, вне Snapshot Layer).

    Реализация предоставляется композицией (тесты — in-memory;
    production — storage-бэкенд). Прямой доступ к Storage запрещён.
    """

    def latest(self, project: str) -> dict[str, object] | None:
        """Последний Snapshot проекта (или None)."""
        ...

    def version(self, project: str, version: str) -> dict[str, object] | None:
        """Snapshot конкретной версии (или None)."""
        ...

    def save(self, project: str, doc: dict[str, object]) -> str:
        """Сохранить новый Snapshot (append-only); возвращает snapshot_id."""
        ...

    def history(self, project: str) -> list[dict[str, object]]:
        """История Snapshot проекта (append-only, от старых к новым)."""
        ...

    def append_history(self, project: str, entry: dict[str, object]) -> None:
        """Добавить запись истории (только append)."""
        ...


class SnapshotLoader:
    """Загрузка Snapshot (latest / version) через порт персистентности.

    Разбор — единый kernel.SnapshotDocument.from_dict (без дублирования
    реализации; Post-Audit Refinement).
    """

    def __init__(self, persistence: SnapshotPersistence) -> None:
        """Инициализация загрузчика.

        Args:
            persistence: Порт персистентности Snapshot (инжектируется).

        """
        self._persistence = persistence

    def load_latest(self, project: str) -> SnapshotDocument | None:
        """Последний стабильный Snapshot проекта.

        Args:
            project: UUID проекта.

        Returns:
            SnapshotDocument или None (снимков нет).

        """
        raw = self._persistence.latest(project)
        if not isinstance(raw, dict):
            return None
        return SnapshotDocument.from_dict(raw)

    def load_version(
        self, project: str, version: str
    ) -> SnapshotDocument:
        """Snapshot указанной версии.

        Args:
            project: UUID проекта.
            version: Номер версии (например, "00041").

        Returns:
            SnapshotDocument.

        Raises:
            SnapshotNotFoundError: версия не существует.

        """
        raw = self._persistence.version(project, version)
        if not isinstance(raw, dict):
            raise SnapshotNotFoundError(
                f"Snapshot version not found: {version!r} for project {project!r}"
            )
        return SnapshotDocument.from_dict(raw)

    @property
    def persistence(self) -> SnapshotPersistence:
        """Порт персистентности."""
        return self._persistence

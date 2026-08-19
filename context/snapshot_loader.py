"""HKOS Snapshot Loader (DS-009, HKOS-10)
=========================================
SnapshotLoader — чтение Snapshot как источника УЖЕ ИЗВЕСТНОГО состояния.

Правила (IP-009):
- Snapshot используется ТОЛЬКО как источник известного состояния;
- Никаких изменений Snapshot; никакой записи Snapshot; только чтение;
- Context Builder не обращается к StorageEngine/JSON напрямую — чтение
  выполняется через инжектированный reader (SnapshotReader), а Loader
  занимается только разбором документа.

Формат Snapshot (HKOS-10 §5): snapshot_id, timestamp, project_id,
campaign_id, references, knowledge_version, index_version, hash...
"""

from typing import Callable, Protocol, runtime_checkable

from hkos.kernel.snapshot_document import SnapshotDocument

__all__ = [
    "SnapshotDocument",  # re-export из hkos.kernel (Post-Audit Refinement)
    "SnapshotReader",
    "SnapshotLoader",
]


@runtime_checkable
class SnapshotReader(Protocol):
    """Порт чтения Snapshot-документов (реализация — вне Context Layer)."""

    def load_latest(self, project_id: str) -> dict[str, object] | None:
        """Прочитать актуальный Snapshot проекта (или None)."""
        ...


class SnapshotLoader:
    """Загрузка Snapshot (read-only) через инжектированный reader."""

    def __init__(
        self,
        reader: Callable[[str], dict[str, object] | None] | None = None,
    ) -> None:
        """Инициализация загрузчика.

        Args:
            reader: Порт чтения Snapshot-документов (инжектируется;
                None — снимки недоступны).

        """
        self._reader = reader

    def load(self, project_id: str) -> SnapshotDocument | None:
        """Прочитать актуальный Snapshot проекта (только чтение).

        Args:
            project_id: UUID проекта.

        Returns:
            SnapshotDocument или None (снимок отсутствует).

        """
        if self._reader is None:
            return None
        raw = self._reader(project_id)
        if not isinstance(raw, dict):
            return None
        return SnapshotDocument.from_dict(raw)

    @property
    def reader(self) -> Callable[[str], dict[str, object] | None] | None:
        """Инжектированный reader."""
        return self._reader

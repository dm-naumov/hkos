"""HKOS Snapshot History (DS-010 §13, IP-010)
===============================================
SnapshotHistory хранит: время создания, автора, кампанию, причину,
комментарий, предыдущую версию. История append-only (IP-010):
удаление и изменение записей запрещены.
"""

from datetime import datetime, timezone

from hkos.snapshot.snapshot_loader import SnapshotPersistence

__all__ = ["SnapshotHistory"]


def _now() -> str:
    """Текущее время ISO-8601 (UTC)."""
    return datetime.now(timezone.utc).isoformat()


class SnapshotHistory:
    """История Snapshot (append-only) через порт персистентности."""

    def __init__(self, persistence: SnapshotPersistence) -> None:
        """Инициализация истории.

        Args:
            persistence: Порт персистентности (append_history).

        """
        self._persistence = persistence

    def append(
        self,
        project: str,
        snapshot_id: str,
        author: str,
        campaign: str,
        reason: str,
        comment: str,
        previous_version: str,
    ) -> dict[str, str]:
        """Добавить запись истории (только append).

        Args:
            project: UUID проекта.
            snapshot_id: ID созданного Snapshot.
            author: Автор.
            campaign: UUID кампании.
            reason: Причина создания.
            comment: Комментарий.
            previous_version: Предыдущая версия ("" — первая).

        Returns:
            Запись истории.

        """
        entry: dict[str, object] = {
            "timestamp": _now(),
            "snapshot_id": snapshot_id,
            "author": author,
            "campaign": campaign,
            "reason": reason,
            "comment": comment,
            "previous_version": previous_version,
        }
        self._persistence.append_history(project, entry)
        return {str(k): str(v) for k, v in entry.items()}

    def entries(self, project: str) -> list[dict[str, str]]:
        """Все записи истории (append-only, от старых к новым)."""
        raw = self._persistence.history(project)
        return [
            {str(k): str(v) for k, v in entry.items()}
            for entry in raw
            if isinstance(entry, dict)
        ]

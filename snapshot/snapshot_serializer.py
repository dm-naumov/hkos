"""HKOS Snapshot Serializer (DS-010 §16, IP-010)
==============================================
Стабильная сериализация Snapshot в JSON-документ (конверт HKOS-08):
schema/type/version/created_at/updated_at/data. Порядок ключей
фиксирован — стабильный вывод.
"""

from hkos.kernel.snapshot_document import SnapshotDocument

__all__ = ["SnapshotSerializer"]

_SCHEMA: str = "HKOS-1.0"
_TYPE: str = "snapshot"
_VERSION: int = 1


class SnapshotSerializer:
    """Сериализация Snapshot (стабильный JSON-конверт HKOS-08)."""

    def serialize(self, snapshot: SnapshotDocument) -> dict[str, object]:
        """Сериализовать Snapshot в документ (конверт HKOS-08).

        Args:
            snapshot: SnapshotDocument.

        Returns:
            dict: стабильный документ (порядок ключей фиксирован).

        """
        return {
            "schema": _SCHEMA,
            "type": _TYPE,
            "version": _VERSION,
            "snapshot_id": snapshot.snapshot_id,
            "timestamp": snapshot.timestamp,
            "project_id": snapshot.project_id,
            "campaign_id": snapshot.campaign_id,
            "parent": snapshot.parent,
            "branch": snapshot.branch,
            "author": snapshot.author,
            "comment": snapshot.comment,
            "knowledge_version": snapshot.knowledge_version,
            "index_version": snapshot.index_version,
            "canonical_version": snapshot.canonical_version,
            "hash": snapshot.hash,
            "references": list(snapshot.references),
            "sections": dict(snapshot.sections),
            "statistics": dict(snapshot.statistics),
        }

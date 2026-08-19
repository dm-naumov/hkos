"""HKOS Snapshot Diff (DS-010 §11, IP-010)
==========================================
SnapshotDiff сравнивает ДВА Snapshot и возвращает:
    Added / Removed / Modified / Unchanged.

Работает ТОЛЬКО поверх Snapshot-документов.
Не имеет права обращаться к Repository (IP-010).
"""

from dataclasses import dataclass, field

from hkos.kernel.snapshot_document import SnapshotDocument

__all__ = ["DiffResult", "SnapshotDiff"]

_COMPARED_SECTIONS: tuple[str, ...] = (
    "Canonical Knowledge",
    "Accepted Decisions",
    "Configurations",
    "Known Failures",
    "Known Limitations",
    "Artifacts",
    "Architecture",
)


@dataclass
class DiffResult:
    """Результат сравнения двух Snapshot."""

    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    section_changes: dict[str, list[str]] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        """Результат как словарь."""
        return {
            "added": self.added,
            "removed": self.removed,
            "modified": self.modified,
            "unchanged": self.unchanged,
            "section_changes": self.section_changes,
        }

    @property
    def changed_count(self) -> int:
        """Число изменённых сущностей (added+removed+modified)."""
        return len(self.added) + len(self.removed) + len(self.modified)


class SnapshotDiff:
    """Сравнение снимков (чистые операции над документами)."""

    @staticmethod
    def _section_index(
        snapshot: SnapshotDocument,
    ) -> dict[str, dict[str, str]]:
        """Индекс (id -> title) по сравниваемым секциям."""
        index: dict[str, dict[str, str]] = {}
        sections = snapshot.sections
        for name in _COMPARED_SECTIONS:
            entries = sections.get(name, [])
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                entity_id = str(entry.get("id", ""))
                if entity_id:
                    index[entity_id] = {
                        "title": str(entry.get("title", "")),
                        "section": name,
                    }
        return index

    def diff(
        self, snapshot_a: SnapshotDocument, snapshot_b: SnapshotDocument
    ) -> DiffResult:
        """Сравнить два снимка (только документы, без Repository).

        Args:
            snapshot_a: Базовый снимок.
            snapshot_b: Новый снимок.

        Returns:
            DiffResult (added/removed/modified/unchanged + по секциям).

        """
        index_a = self._section_index(snapshot_a)
        index_b = self._section_index(snapshot_b)

        result = DiffResult()
        section_changes: dict[str, list[str]] = {}

        for entity_id, meta_b in index_b.items():
            meta_a = index_a.get(entity_id)
            if meta_a is None:
                result.added.append(entity_id)
            elif meta_a != meta_b:
                result.modified.append(entity_id)
            else:
                result.unchanged.append(entity_id)
            if meta_a is None or meta_a != meta_b:
                section = meta_b["section"]
                section_changes.setdefault(section, []).append(entity_id)

        for entity_id in index_a:
            if entity_id not in index_b:
                result.removed.append(entity_id)
                section = index_a[entity_id]["section"]
                section_changes.setdefault(section, []).append(entity_id)

        result.added.sort()
        result.removed.sort()
        result.modified.sort()
        result.unchanged.sort()
        result.section_changes = {
            name: sorted(ids) for name, ids in section_changes.items()
        }
        return result

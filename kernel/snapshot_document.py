"""HKOS Snapshot Document (Kernel — общий тип нижнего уровня)
=================================================================
SnapshotDocument вынесен из Context Layer в Kernel (Post-Audit
Refinement, замечание о владении схемой: производитель Snapshot Engine
не должен зависеть от потребителя Context). Context и Snapshot
зависят от Kernel; в Context сохранён re-export для обратной
совместимости импортов.

Формат — HKOS-10 §5; расширения DS-010 (sections/statistics/author/
comment/branch/parent).
"""

from dataclasses import dataclass, field

__all__ = ["SnapshotDocument"]


@dataclass
class SnapshotDocument:
    """Документ Snapshot (только чтение, HKOS-10)."""

    snapshot_id: str = ""
    timestamp: str = ""
    project_id: str = ""
    campaign_id: str = ""
    references: list[str] = field(default_factory=list)
    knowledge_version: str = ""
    index_version: str = ""
    canonical_version: str = ""
    hash: str = ""
    # --- Аддитивное расширение (DS-010 Snapshot Engine, HKOS-10 §9/§14) ---
    author: str = ""
    comment: str = ""
    branch: str = ""
    parent: str = ""
    sections: dict[str, object] = field(default_factory=dict)
    statistics: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "SnapshotDocument":
        """Документ из словаря (разбор без I/O).

        Расширение аддитивно: старые документы (без новых ключей)
        разбираются с прежним поведением.
        """
        references = data.get("references", [])
        sections = data.get("sections", {})
        statistics = data.get("statistics", {})
        return cls(
            snapshot_id=str(data.get("snapshot_id", "")),
            timestamp=str(data.get("timestamp", "")),
            project_id=str(data.get("project_id", "")),
            campaign_id=str(data.get("campaign_id", "")),
            references=(
                [str(r) for r in references] if isinstance(references, list) else []
            ),
            knowledge_version=str(data.get("knowledge_version", "")),
            index_version=str(data.get("index_version", "")),
            canonical_version=str(data.get("canonical_version", "")),
            hash=str(data.get("hash", "")),
            author=str(data.get("author", "")),
            comment=str(data.get("comment", "")),
            branch=str(data.get("branch", "")),
            parent=str(data.get("parent", "")),
            sections=(
                dict(sections) if isinstance(sections, dict) else {}
            ),
            statistics=(
                {str(k): int(v) for k, v in statistics.items()}
                if isinstance(statistics, dict)
                else {}
            ),
        )

    def as_dict(self) -> dict[str, object]:
        """Документ как словарь."""
        return {
            "snapshot_id": self.snapshot_id,
            "timestamp": self.timestamp,
            "project_id": self.project_id,
            "campaign_id": self.campaign_id,
            "references": self.references,
            "knowledge_version": self.knowledge_version,
            "index_version": self.index_version,
            "canonical_version": self.canonical_version,
            "hash": self.hash,
            "author": self.author,
            "comment": self.comment,
            "branch": self.branch,
            "parent": self.parent,
            "sections": self.sections,
            "statistics": self.statistics,
        }

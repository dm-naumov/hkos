"""HKOS Context Models (DS-009)
==============================
Типы документа контекста: ContextItem, ContextDocument,
ContextExplanation. Модуль добавлен аддитивно (типы используются
всеми компонентами Context Layer без циклических импортов).
"""

from dataclasses import dataclass, field
from typing import Any

from hkos.context.token_estimator import TokenEstimate
from hkos.kernel.snapshot_document import SnapshotDocument

__all__ = ["ContextItem", "ContextDocument", "ContextExplanation"]


@dataclass
class ContextItem:
    """Элемент контекста с объяснением включения/исключения."""

    entity: Any  # Knowledge | Decision | Artifact
    entity_type: str
    source: str = "retrieval"  # retrieval | snapshot | canonical
    reason: str = ""
    excluded_reason: str = ""
    score: float = 0.0
    relation_path: list[str] = field(default_factory=list)
    matched_topic: str = ""
    matched_keywords: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        """Элемент как словарь."""
        return {
            "id": getattr(self.entity, "id", ""),
            "type": self.entity_type,
            "title": (
                getattr(self.entity, "title", "")
                or getattr(self.entity, "name", "")
            ),
            "source": self.source,
            "reason": self.reason,
            "excluded_reason": self.excluded_reason,
            "score": round(self.score, 2),
        }


@dataclass
class ContextDocument:
    """Документ контекста (результат Context Builder)."""

    task: str = ""
    project_id: str = ""
    campaign_id: str = ""
    profile: str = "MEDIUM"
    snapshot: SnapshotDocument | None = None
    items: list[ContextItem] = field(default_factory=list)
    excluded: list[ContextItem] = field(default_factory=list)
    estimates: TokenEstimate = field(default_factory=TokenEstimate)
    sections: dict[str, list[ContextItem]] = field(default_factory=dict)
    validation: Any = None

    def as_dict(self) -> dict[str, object]:
        """Документ как словарь."""
        return {
            "task": self.task,
            "project_id": self.project_id,
            "campaign_id": self.campaign_id,
            "profile": self.profile,
            "snapshot": self.snapshot.as_dict() if self.snapshot else None,
            "items": [item.as_dict() for item in self.items],
            "excluded": [item.as_dict() for item in self.excluded],
            "estimates": self.estimates.as_dict(),
            "sections": {
                name: [i.as_dict() for i in items]
                for name, items in self.sections.items()
            },
        }


@dataclass
class ContextExplanation:
    """Объяснение элемента контекста (IP-009: почему/источник/экономия)."""

    entity_id: str = ""
    why_included: str = ""
    why_excluded: str = ""
    source: str = ""
    token_savings: int = 0

    def as_dict(self) -> dict[str, object]:
        """Объяснение как словарь."""
        return {
            "entity_id": self.entity_id,
            "why_included": self.why_included,
            "why_excluded": self.why_excluded,
            "source": self.source,
            "token_savings": self.token_savings,
        }

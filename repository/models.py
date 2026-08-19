"""HKOS Repository Models (DS-003)
=================================
Объекты предметной области, с которыми работает слой Repository.

Поля сущностей соответствуют разделам data форматов HKOS-08
(project, campaign, knowledge, decision, artifact).
Константы жизненных циклов — по HKOS-03 (§16 Knowledge, §17 Decision).

Модели не содержат поведения — это контейнеры данных.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from hkos.repository.knowledge_relations import (
    KnowledgeRelation,
    RelationType,
)

__all__ = [
    "Project",
    "Campaign",
    "Knowledge",
    "Decision",
    "Artifact",
    "CampaignState",
    "CampaignMetadata",
    "DecisionHistory",
    "PROJECT_STATUS_ACTIVE",
    "PROJECT_STATUS_ARCHIVED",
    "CAMPAIGN_STATUS_ACTIVE",
    "CAMPAIGN_STATUS_COMPLETED",
    "CAMPAIGN_STATUS_CLOSED",
    "CAMPAIGN_STATUS_ARCHIVED",
    "CampaignStep",
    "JournalEntry",
    "KnowledgeHistoryEntry",
    "KnowledgeRelation",
    "RelationType",
    "KNOWLEDGE_STATUS_NEW",
    "KNOWLEDGE_STATUS_CANDIDATE",
    "KNOWLEDGE_STATUS_UNDER_REVIEW",
    "KNOWLEDGE_STATUS_VALIDATED",
    "KNOWLEDGE_STATUS_CANONICAL",
    "KNOWLEDGE_STATUS_SUPERSEDED",
    "KNOWLEDGE_STATUS_ARCHIVED",
    "ARTIFACT_STATUS_ACTIVE",
    "ARTIFACT_STATUS_ARCHIVED",
    "DECISION_ACCEPT",
    "DECISION_REJECT",
]

# --- Project (HKOS-08 §3) ---
PROJECT_STATUS_ACTIVE: str = "active"
PROJECT_STATUS_ARCHIVED: str = "archived"

# --- Campaign (HKOS-08 §4) ---
CAMPAIGN_STATUS_ACTIVE: str = "active"
CAMPAIGN_STATUS_COMPLETED: str = "completed"
CAMPAIGN_STATUS_CLOSED: str = "closed"
CAMPAIGN_STATUS_ARCHIVED: str = "archived"

# --- Knowledge lifecycle (HKOS-03 §16) ---
KNOWLEDGE_STATUS_NEW: str = "new"
KNOWLEDGE_STATUS_CANDIDATE: str = "candidate"
KNOWLEDGE_STATUS_UNDER_REVIEW: str = "under_review"
KNOWLEDGE_STATUS_VALIDATED: str = "validated"
KNOWLEDGE_STATUS_CANONICAL: str = "canonical"
KNOWLEDGE_STATUS_SUPERSEDED: str = "superseded"
KNOWLEDGE_STATUS_ARCHIVED: str = "archived"

# --- Artifact status ---
ARTIFACT_STATUS_ACTIVE: str = "active"
ARTIFACT_STATUS_ARCHIVED: str = "archived"

# --- Decision value (HKOS-08 §8) ---
DECISION_ACCEPT: str = "ACCEPT"
DECISION_REJECT: str = "REJECT"


@dataclass
class Project:
    """Проект — независимая инженерная предметная область (HKOS-03 §5).

    Метаданные DS-004 (§11): owner, schema_version, statistics добавлены
    аддитивно (обратно совместимо); created_at/updated_at заполняются
    из конверта HKOS-08 при чтении документа.
    """

    id: str = ""
    name: str = ""
    description: str = ""
    status: str = PROJECT_STATUS_ACTIVE
    tags: list[str] = field(default_factory=list)
    current_snapshot: str = ""
    campaigns: list[str] = field(default_factory=list)
    owner: str = ""
    schema_version: str = "1.0"
    statistics: dict[str, object] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""


@dataclass
class Campaign:
    """Исследовательская кампания проекта (HKOS-03 §7)."""

    id: str = ""
    project: str = ""
    goal: str = ""
    status: str = CAMPAIGN_STATUS_ACTIVE
    cycles: int = 0
    snapshot: str = ""
    worker_reports: list[str] = field(default_factory=list)
    boss_reports: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    schema_version: str = "1.0"
    steps: list[CampaignStep] = field(default_factory=list)
    journal: list[JournalEntry] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""


@dataclass
class Knowledge:
    """Инженерный факт, подтверждённый Evidence (HKOS-03 §11)."""

    id: str = ""
    project: str = ""
    kind: str = "fact"
    title: str = ""
    body: str = ""
    confidence: int = 0
    status: str = KNOWLEDGE_STATUS_NEW
    source_campaign: str = ""
    source_cycle: int = 0
    references: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    category: str = ""
    parent_ids: list[str] = field(default_factory=list)
    canonical_id: str = ""
    confirmations: int = 0
    independent_campaigns: int = 0
    successful_usage: int = 0
    failed_usage: int = 0
    conflicts: int = 0
    history: list[KnowledgeHistoryEntry] = field(default_factory=list)
    relations: list[KnowledgeRelation] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""


@dataclass
class Decision:
    """Инженерное решение, основанное на Knowledge (HKOS-03 §13)."""

    id: str = ""
    project: str = ""
    decision: str = DECISION_ACCEPT
    campaign: str = ""
    cycle: int = 0
    reason: str = ""
    confidence: int = 0


@dataclass
class Artifact:
    """Первичный материал проекта (HKOS-03 §9)."""

    id: str = ""
    project: str = ""
    kind: str = ""
    path: str = ""
    checksum: str = ""
    campaign: str = ""
    cycle: int = 0
    status: str = ARTIFACT_STATUS_ACTIVE


@dataclass
class CampaignState:
    """Состояние кампании (результат close/archive)."""

    status: str = ""
    updated_at: str = ""


@dataclass
class CampaignMetadata:
    """Метаданные документа кампании (из конверта HKOS-08)."""

    created_at: str = ""
    updated_at: str = ""
    version: int = 0


@dataclass
class DecisionHistory:
    """История решений проекта (append-only)."""

    entries: list[Decision] = field(default_factory=list)


@dataclass
class CampaignStep:
    """Этап кампании (источник истины для Progress, DS-005 §11).

    Статус этапа: pending | running | completed | failed.
    retries — количество повторов этапа (для Statistics.retry_count).
    """

    id: str = ""
    title: str = ""
    status: str = "pending"
    retries: int = 0

    def to_dict(self) -> dict[str, object]:
        """Этап как словарь (сериализация)."""
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "retries": self.retries,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "CampaignStep":
        """Этап из словаря (десериализация)."""
        retries_raw = data.get("retries", 0)
        retries = retries_raw if isinstance(retries_raw, int) else 0
        return cls(
            id=str(data.get("id", "")),
            title=str(data.get("title", "")),
            status=str(data.get("status", "pending")),
            retries=retries,
        )


@dataclass
class KnowledgeHistoryEntry:
    """Запись истории Knowledge (append-only, DS-006 §15)."""

    timestamp: str = ""
    knowledge_id: str = ""
    event: str = ""
    details: str = ""

    def to_dict(self) -> dict[str, object]:
        """Запись как словарь (сериализация)."""
        return {
            "timestamp": self.timestamp,
            "knowledge_id": self.knowledge_id,
            "event": self.event,
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "KnowledgeHistoryEntry":
        """Запись из словаря (десериализация)."""
        return cls(
            timestamp=str(data.get("timestamp", "")),
            knowledge_id=str(data.get("knowledge_id", "")),
            event=str(data.get("event", "")),
            details=str(data.get("details", "")),
        )


@dataclass
class JournalEntry:
    """Запись журнала кампании (append-only, IP-005 §13)."""

    timestamp: str = ""
    campaign_id: str = ""
    event: str = ""
    details: str = ""

    def to_dict(self) -> dict[str, object]:
        """Запись как словарь (сериализация)."""
        return {
            "timestamp": self.timestamp,
            "campaign_id": self.campaign_id,
            "event": self.event,
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "JournalEntry":
        """Запись из словаря (десериализация)."""
        return cls(
            timestamp=str(data.get("timestamp", "")),
            campaign_id=str(data.get("campaign_id", "")),
            event=str(data.get("event", "")),
            details=str(data.get("details", "")),
        )

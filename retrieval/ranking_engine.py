"""HKOS Ranking Engine (DS-008 §10, IP-008)
=========================================
Детерминированное ранжирование кандидатов.

Все ВЕСОВЫЕ КОЭФФИЦИЕНТЫ вынесены в конфигурацию (retrieval.ranking.*).
В коде НЕТ захардкоженных коэффициентов (проверяется архитектурным тестом).

Факторы (IP-008): Topic, Confidence, Project, Freshness, Usage,
Canonical, References, Success Count, Campaign Match, Decision Priority.

Каждый фактор нормализован в [0, 1]; итоговый Score = sum(weight * factor) * 100.

Сортировка детерминированная: (score desc, id asc).

Candidate-сущности читаются через RepositoryManager по UUID
(контракт Section 3: Repository только для выбранных UUID).

TODO (DS-011, Memory/Migration): Stub-entities за пределами
refine_limit попадают в RetrievalResult с entity-заглушкой из Q3
(confidence=0, body="") — Managed Technical Debt (Freeze Audit v2,
наблюдение про refine_limit). Измерения: last_stats
(candidates/refined/stub) позволяют оценить необходимость увеличения
refine_limit.
Remove when: измерение stub_in_top_n стабильно равно нулю при
реальной нагрузке, или refine_limit пересчитан по измерениям.
"""

from datetime import datetime, timezone
from math import exp
from typing import Any, Mapping

from hkos.repository.models import Knowledge
from hkos.repository.repository_manager import RepositoryManager
from hkos.retrieval.candidate_builder import CandidateSet
from hkos.retrieval.query_parser import ParsedQuery
from hkos.services.librarian.knowledge_status import (
    KnowledgeStatus,
)

__all__ = ["RankedCandidate", "RankingEngine"]

_SCORE_MIN: int = 0
_SCORE_MAX: int = 100
_CONFIDENCE_DIVISOR: int = 100


class RankedCandidate:
    """Кандидат с итоговым рейтингом и разложением по факторам."""

    def __init__(
        self,
        entity: Knowledge,
        entity_type: str,
        score: float,
        factors: Mapping[str, float],
        sources: list[str] | None = None,
        relation_path: list[str] | None = None,
    ) -> None:
        """Инициализация ранжированного кандидата."""
        self.entity = entity
        self.entity_type = entity_type
        self.score = score
        self.factors: dict[str, float] = dict(factors)
        self.sources: list[str] = list(sources or [])
        self.relation_path: list[str] = list(relation_path or [])


class RankingEngine:
    """Ранжирование кандидатов (детерминированное, конфигурируемое)."""

    def __init__(
        self,
        repositories: RepositoryManager,
        weights: Mapping[str, float],
        caps: Mapping[str, int] | None = None,
        half_life_days: float = 90,
    ) -> None:
        """Инициализация ранжировщика.

        Args:
            repositories: RepositoryManager (чтение сущностей по UUID).
            weights: Весовые коэффициенты факторов (ИЗ КОНФИГУРАЦИИ).
            caps: Верхние границы нормализации (из конфигурации).
            half_life_days: Период полураспада свежести (из конфигурации).

        """
        self._repositories = repositories
        self._weights = dict(weights)
        self._caps = dict(caps or {})
        self._half_life_days = half_life_days
        # Диагностика (DS-009A, задача 3): измерения двухфазного
        # ранжирования — candidates/refined/stub. Публичный API не изменён.
        self._last_stats: dict[str, int] = {}

    # --- Загрузка сущностей (только по UUID, контракт Section 3) ---

    def _load_entity(
        self, project: str, entity_id: str, entity_type: str
    ) -> Any:
        """Загрузить сущность по UUID через RepositoryManager.

        Returns:
            Knowledge | Decision | Artifact | Campaign (или None).

        """
        if entity_type == "knowledge":
            return self._repositories.knowledge.load(project, entity_id)
        if entity_type == "decision":
            return self._repositories.decisions.load(project, entity_id)
        if entity_type == "artifact":
            return self._repositories.artifacts.load(project, entity_id)
        if entity_type == "campaign":
            return self._repositories.campaigns.load(project, entity_id)
        return None

    # --- Факторы ---

    @staticmethod
    def _text(entity: Any) -> str:
        """Смысловой текст сущности (getattr-безопасно для всех типов)."""
        parts: list[str] = []
        for attr in ("title", "name", "goal", "decision", "reason",
                     "category", "kind", "body", "description"):
            value = getattr(entity, attr, None)
            if value:
                parts.append(str(value).lower())
        for tag in (getattr(entity, "tags", None) or []):
            parts.append(str(tag).lower())
        return " ".join(parts)

    def _topic_factor(self, entity: Any, topic: str) -> float:
        """Совпадение темы (текст сущности)."""
        if not topic:
            return 1
        return 1 if topic in self._text(entity) else 0

    def _freshness_factor(self, updated_at: str) -> float:
        """Свежесть: экспоненциальный распад по возрасту (дни)."""
        if not updated_at:
            return 1
        try:
            parsed = datetime.fromisoformat(updated_at)
        except ValueError:
            return 1
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        age_days = max(0, (datetime.now(timezone.utc) - parsed).total_seconds() / 86400)
        if self._half_life_days <= 0:
            return 1
        return exp(-age_days / self._half_life_days)

    def _normalized(self, value: int, cap_key: str) -> float:
        """Нормализация значения по верхней границе из конфигурации."""
        cap = self._caps.get(cap_key, 0)
        if cap <= 0:
            return 0
        return min(float(value), float(cap)) / float(cap)

    def _score(
        self,
        entity: Knowledge,
        entity_type: str,
        parsed: ParsedQuery,
        project: str | None,
        campaign_id: str | None,
    ) -> tuple[float, dict[str, float]]:
        """Итоговый score и разложение по факторам."""
        factors: dict[str, float] = {
            "topic": self._topic_factor(entity, parsed.topic),
            "confidence": min(
                float(entity.confidence), float(_CONFIDENCE_DIVISOR)
            ) / float(_CONFIDENCE_DIVISOR),
            "project": 1 if (project is None or entity.project == project) else 0,
            "freshness": self._freshness_factor(entity.updated_at),
            "usage": self._normalized(entity.successful_usage, "usage"),
            "canonical": 1 if KnowledgeStatus.is_canonical(entity) else 0,
            "references": self._normalized(len(entity.references), "references"),
            "success": self._normalized(entity.confirmations, "confirmations"),
            "campaign": 1 if (campaign_id and entity.source_campaign == campaign_id) else 0,
            "decision": 1 if entity_type == "decision" else 0,
        }
        score = sum(
            self._weights.get(name, 0) * value
            for name, value in factors.items()
        )
        score = max(float(_SCORE_MIN), min(float(_SCORE_MAX), score * float(_SCORE_MAX)))
        return score, factors

    def score(
        self,
        entity: Knowledge,
        entity_type: str,
        parsed: ParsedQuery,
        project: str | None = None,
        campaign_id: str | None = None,
    ) -> tuple[float, dict[str, float]]:
        """Публичный расчёт score для одной сущности (explain)."""
        return self._score(entity, entity_type, parsed, project, campaign_id)

    def rank(
        self,
        candidates: CandidateSet,
        parsed: ParsedQuery,
        project: str | None = None,
        campaign_id: str | None = None,
        snapshot: Any | None = None,
        refine_limit: int = 60,
    ) -> list[RankedCandidate]:
        """Ранжировать кандидатов (двухфазно, детерминированно).

        Фаза 1 (только индекс, Q3): topic/project/freshness/canonical/
        decision — БЕЗ чтения документов (HKOS-09 §17).
        Фаза 2 (Top-K): загрузка refine_limit сущностей по UUID для
        полных факторов (confidence/usage/references/success/campaign).

        Args:
            candidates: Набор кандидатов из Candidate Builder.
            parsed: Разобранный запрос.
            project: UUID проекта.
            campaign_id: UUID кампании (фактор Campaign Match).
            query: Query Contract (Q3) для index-only фазы.
            refine_limit: Число кандидатов, загружаемых по UUID.

        Returns:
            RankedCandidate, отсортированные по (score desc, id asc).

        """
        # --- Фаза 1: index-only scoring (Q3, без чтения документов) ---
        phased: list[tuple[RankedCandidate, float]] = []
        for entry in candidates.entries:
            if snapshot is not None:
                record = snapshot.entity_get(entry.id)
                if record is None:
                    continue
                candidate = RankedCandidate(
                    entity=Knowledge(
                        id=record.id, project=record.project,
                        title=record.title, status=record.status,
                        category=record.category, tags=record.tags,
                        updated_at=record.updated_at,
                    ),
                    entity_type=entry.type,
                    score=0,
                    factors={},
                    sources=candidates.sources.get(entry.id, []),
                )
            else:
                entity = self._load_entity(project or "", entry.id, entry.type)
                if entity is None:
                    continue
                candidate = RankedCandidate(
                    entity=entity,
                    entity_type=entry.type,
                    score=0,
                    factors={},
                    sources=candidates.sources.get(entry.id, []),
                )
            score1, factors1 = self._score_index_only(
                candidate, parsed, project
            )
            candidate.score = score1
            candidate.factors = factors1
            phased.append((candidate, score1))

        phased.sort(key=lambda pair: (-pair[1], pair[0].entity.id))

        # --- Фаза 2: полный score для Top-K (загрузка по UUID) ---
        ranked: list[RankedCandidate] = []
        for index, (candidate, score1) in enumerate(phased):
            # DS-016 ЭТАП 2 (defect fix): кандидаты-контекст (campaign/
            # project, попавшие через tag/keyword) не являются результатами
            # retrieval — пропускаются (иначе _score падает: у Campaign
            # нет confidence/updated_at). DECISION/ARTIFACT остаются.
            if candidate.entity_type in ("campaign", "project"):
                continue
            if index < refine_limit:
                entity = self._load_entity(
                    project or "", candidate.entity.id, candidate.entity_type
                )
                if entity is not None:
                    candidate.entity = entity
                    score, factors = self._score(
                        entity, candidate.entity_type, parsed,
                        project, campaign_id,
                    )
                    candidate.score = score
                    candidate.factors = factors
            ranked.append(candidate)

        ranked.sort(key=lambda c: (-c.score, c.entity.id))

        # Диагностика (DS-009A, задача 3)
        self._last_stats = {
            "candidates": len(phased),
            "refined": min(len(phased), refine_limit),
            "stub": max(0, len(phased) - refine_limit),
        }
        return ranked

    @property
    def last_stats(self) -> dict[str, int]:
        """Измерения последнего ранжирования (candidates/refined/stub)."""
        return dict(self._last_stats)

    def _score_index_only(
        self,
        candidate: RankedCandidate,
        parsed: ParsedQuery,
        project: str | None,
    ) -> tuple[float, dict[str, float]]:
        """Index-only факторы (Q3): topic/project/freshness/canonical/decision."""
        entity = candidate.entity
        factors: dict[str, float] = {
            "topic": self._topic_factor(entity, parsed.topic),
            "project": 1 if (project is None or entity.project == project) else 0,
            "freshness": self._freshness_factor(entity.updated_at),
            "canonical": 1 if KnowledgeStatus.is_canonical(entity) else 0,
            "decision": 1 if candidate.entity_type == "decision" else 0,
        }
        score = sum(
            self._weights.get(name, 0) * value
            for name, value in factors.items()
        ) * float(_SCORE_MAX)
        return score, factors

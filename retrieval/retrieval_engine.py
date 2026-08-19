"""HKOS Retrieval Engine (DS-008 §4-6, §16)
=========================================
Публичный фасад Retrieval Layer.

Публичный API (ровно эти методы, стабильные сигнатуры):
    retrieve, search, search_project, search_campaign,
    related, explain, statistics

Retrieval использует ИСКЛЮЧИТЕЛЬНО:
    - RepositoryManager (чтение сущностей ТОЛЬКО по UUID);
    - Query Contract (Q1-Q5, HKOS-INDEX-CONTRACT-001 FROZEN).

Запрещено: StorageEngine, Filesystem, JSON, SQLite,
Repository.list()/walk()/scan(), IndexStore (проверяется
архитектурными тестами).
"""

import time
from dataclasses import dataclass, field
from typing import Mapping

from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.index.query_contract import IndexQueryExecutor
from hkos.repository.models import Knowledge
from hkos.repository.repository_manager import RepositoryManager
from hkos.retrieval.candidate_builder import CandidateBuilder
from hkos.retrieval.exceptions import RetrievalError, RetrievalScopeError
from hkos.retrieval.knowledge_filter import KnowledgeFilter
from hkos.retrieval.knowledge_selector import KnowledgeSelector
from hkos.retrieval.query_parser import ParsedQuery, QueryParser
from hkos.retrieval.ranking_engine import RankedCandidate, RankingEngine
from hkos.retrieval.relationship_traverser import RelationshipTraverser
from hkos.retrieval.retriever import Retriever

__all__ = [
    "RetrievalExplanation",
    "RetrievalItem",
    "RetrievalResult",
    "RetrievalEngine",
]


@dataclass
class RetrievalExplanation:
    """Объяснение выбора Knowledge (DS-008 §15, IP-008)."""

    reason: str = ""
    score: float = 0.0
    matched_keywords: list[str] = field(default_factory=list)
    matched_topic: str = ""
    confidence: int = 0
    canonical: bool = False
    project_match: bool = False
    campaign_match: bool = False
    relation_path: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        """Объяснение как словарь."""
        return {
            "reason": self.reason,
            "score": round(self.score, 2),
            "matched_keywords": self.matched_keywords,
            "matched_topic": self.matched_topic,
            "confidence": self.confidence,
            "canonical": self.canonical,
            "project_match": self.project_match,
            "campaign_match": self.campaign_match,
            "relation_path": self.relation_path,
        }


@dataclass
class RetrievalItem:
    """Выбранное Knowledge с объяснением."""

    entity: Knowledge
    entity_type: str
    explanation: RetrievalExplanation

    def as_dict(self) -> dict[str, object]:
        """Элемент результата как словарь."""
        return {
            "id": self.entity.id,
            "type": self.entity_type,
            "title": self.entity.title,
            "status": self.entity.status,
            "confidence": self.entity.confidence,
            "explanation": self.explanation.as_dict(),
        }


@dataclass
class RetrievalResult:
    """Результат Retrieval (минимально достаточный контекст)."""

    query: str
    project: str = ""
    items: list[RetrievalItem] = field(default_factory=list)
    duration_ms: float = 0.0
    total_candidates: int = 0

    def as_dict(self) -> dict[str, object]:
        """Результат как словарь."""
        return {
            "query": self.query,
            "project": self.project,
            "duration_ms": round(self.duration_ms, 2),
            "total_candidates": self.total_candidates,
            "items": [item.as_dict() for item in self.items],
        }


class RetrievalEngine:
    """Публичный фасад Retrieval Engine (только Query Contract + RepositoryManager)."""

    def __init__(
        self,
        repositories: RepositoryManager,
        query: IndexQueryExecutor,
        config: ConfigLoader,
        logger: HKOSLogger,
        project_registry: Mapping[str, str] | None = None,
    ) -> None:
        """Инициализация Retrieval Engine.

        Args:
            repositories: RepositoryManager (сущности по UUID).
            query: Query Contract (Q1-Q5, FROZEN).
            config: ConfigLoader (секция retrieval.*).
            logger: HKOSLogger.
            project_registry: Имя проекта -> UUID (для project_hint).

        """
        self._repositories = repositories
        self._query = query
        self._config = config
        self._logger = logger
        self._project_registry: Mapping[str, str] = dict(project_registry or {})
        self._retrieval_count = 0

        # --- Конфигурация (все коэффициенты из config, не из кода) ---
        ranking_cfg = "retrieval.ranking"
        weights: dict[str, float] = {}
        for name in ("topic", "confidence", "project", "freshness", "usage",
                     "canonical", "references", "success", "campaign", "decision"):
            value = config.get(f"{ranking_cfg}.{name}_weight", 0.0)
            weights[name] = float(value) if isinstance(value, (int, float)) else 0.0
        caps: dict[str, int] = {}
        for name in ("usage", "references", "confirmations"):
            value = config.get(f"{ranking_cfg}.{name}_cap", 0)
            caps[name] = int(value) if isinstance(value, (int, float)) else 0
        half_life = config.get(f"{ranking_cfg}.freshness_half_life_days", 90)
        half_life_days = float(half_life) if isinstance(half_life, (int, float)) else 90.0

        top_n = config.get("retrieval.selector.top_n", 20)
        self._top_n: int = int(top_n) if isinstance(top_n, int) else 20
        max_candidates = config.get("retrieval.builder.max_candidates", 200)
        self._max_candidates: int = (
            int(max_candidates) if isinstance(max_candidates, int) else 200
        )
        keyword_limit = config.get("retrieval.builder.keyword_limit", 50)
        keyword_limit = int(keyword_limit) if isinstance(keyword_limit, int) else 50
        max_depth = config.get("retrieval.traverser.max_depth", 1)
        self._max_depth: int = int(max_depth) if isinstance(max_depth, int) else 1
        max_related = config.get("retrieval.traverser.max_related", 10)
        max_related = int(max_related) if isinstance(max_related, int) else 10
        decay = config.get("retrieval.traverser.relation_decay", 0.8)
        relation_decay = float(decay) if isinstance(decay, (int, float)) else 0.8

        # --- Конвейер (стадии инжектируются в Retriever) ---
        parser = QueryParser(config)
        builder = CandidateBuilder(self._max_candidates, keyword_limit)
        # Audit Remediation DS-009A (задача 4): базовое число кандидатов
        # фазы-2 ранжирования — из конфигурации (поведение не изменено).
        refine_base = config.get("retrieval.ranking.refine_limit_base", 60)
        refine_base = int(refine_base) if isinstance(refine_base, int) else 60
        self._refine_limit = max(refine_base, self._top_n * 3)
        ranking = RankingEngine(
            repositories, weights, caps, half_life_days
        )
        filter_ = KnowledgeFilter()
        traverser = RelationshipTraverser(
            repositories, self._max_depth, max_related, relation_decay
        )
        selector = KnowledgeSelector()
        self._retriever = Retriever(
            parser, builder, ranking, filter_, traverser, selector
        )

    # --- Внутренние ---

    def _resolve_project(
        self, project_id: str | None, project_hint: str = ""
    ) -> str:
        """Определить UUID проекта (explicit > hint-реестр > единственный)."""
        if project_id:
            return project_id
        if project_hint and project_hint.lower() in self._project_registry:
            return self._project_registry[project_hint.lower()]
        if len(self._project_registry) == 1:
            return next(iter(self._project_registry.values()))
        raise RetrievalScopeError(
            "Project scope required: pass project_id or configure "
            "project_registry (HKOS-09 §7: project-first search)"
        )

    def _to_result(
        self,
        query_text: str,
        project: str,
        candidates: list[RankedCandidate],
        matched_keywords: list[str],
        matched_topic: str,
        parsed: ParsedQuery,
        campaign_id: str | None,
        start: float,
        total_candidates: int,
    ) -> RetrievalResult:
        """Собрать RetrievalResult с объяснениями (Explainability)."""
        items: list[RetrievalItem] = []
        for candidate in candidates:
            factors = candidate.factors
            explanation = RetrievalExplanation(
                reason=self._explain_reason(candidate, factors),
                score=candidate.score,
                matched_keywords=matched_keywords,
                matched_topic=matched_topic,
                confidence=candidate.entity.confidence,
                canonical=(
                    factors.get("canonical", 0.0) > 0.0
                ),
                project_match=(
                    factors.get("project", 0.0) > 0.0
                ),
                campaign_match=(
                    factors.get("campaign", 0.0) > 0.0
                ),
                relation_path=candidate.relation_path,
            )
            items.append(
                RetrievalItem(
                    entity=candidate.entity,
                    entity_type=candidate.entity_type,
                    explanation=explanation,
                )
            )
        return RetrievalResult(
            query=query_text,
            project=project,
            items=items,
            duration_ms=(time.monotonic() - start) * 1000.0,
            total_candidates=total_candidates,
        )

    @staticmethod
    def _explain_reason(
        candidate: RankedCandidate, factors: Mapping[str, float]
    ) -> str:
        """Причина выбора (человекочитаемая)."""
        parts: list[str] = []
        if factors.get("topic", 0.0) > 0.0:
            parts.append("Topic Match")
        if factors.get("canonical", 0.0) > 0.0:
            parts.append("Canonical")
        if factors.get("project", 0.0) > 0.0:
            parts.append("Project Match")
        if factors.get("campaign", 0.0) > 0.0:
            parts.append("Campaign Match")
        if factors.get("confidence", 0.0) > 0.0:
            parts.append("Confidence")
        if candidate.relation_path:
            parts.append("Related")
        return ", ".join(parts) if parts else "Keyword Match"

    def _load_knowledge(self, project_id: str, knowledge_id: str) -> Knowledge:
        """Загрузить Knowledge по UUID (обёртка репозиторных ошибок)."""
        try:
            return self._repositories.knowledge.load(project_id, knowledge_id)
        except Exception as e:  # noqa: BLE001 — ошибка репозитория -> RetrievalError
            raise RetrievalError(
                f"Knowledge not found: {knowledge_id}"
            ) from e

    # --- Публичный API ---

    def retrieve(
        self,
        query: str,
        project_id: str | None = None,
        campaign_id: str | None = None,
        top_n: int | None = None,
        include_history: bool = False,
    ) -> RetrievalResult:
        """Полный конвейер Retrieval (с обходом связей)."""
        self._retrieval_count += 1
        self._logger.info(f"Retrieval Started: {query!r}")
        start = time.monotonic()
        parsed = QueryParser(self._config).parse(query)
        project = self._resolve_project(project_id, parsed.project_hint)
        snapshot = self._query.snapshot(project)
        candidates = self._retriever.run_parsed(
            parsed,
            project=project,
            campaign_id=campaign_id,
            top_n=top_n if top_n is not None else self._top_n,
            include_history=include_history,
            snapshot=snapshot,
            refine_limit=self._refine_limit,
        )
        self._logger.info(f"Candidates Built: {len(candidates)}")
        self._logger.info("Ranking Completed")
        self._logger.info("Filter Applied")
        self._logger.info("Knowledge Selected")
        self._logger.info("Context Sent")
        return self._to_result(
            query, project, candidates,
            parsed.keywords, parsed.topic, parsed, campaign_id,
            start, len(candidates),
        )

    def search(
        self,
        query: str,
        project_id: str | None = None,
        campaign_id: str | None = None,
        top_n: int | None = None,
        include_history: bool = False,
    ) -> RetrievalResult:
        """Поиск без обхода связей (прямой конвейер: parser->builder->rank->filter->select).

        Отличие от retrieve(): Relationship Traverser пропускается.
        """
        self._retrieval_count += 1
        self._logger.info(f"Retrieval Started (search): {query!r}")
        start = time.monotonic()
        parsed = QueryParser(self._config).parse(query)
        project = self._resolve_project(project_id, parsed.project_hint)
        snapshot = self._query.snapshot(project)
        selected = self._retriever.run_search(
            query,
            project=project,
            campaign_id=campaign_id,
            top_n=top_n if top_n is not None else self._top_n,
            include_history=include_history,
            snapshot=snapshot,
            refine_limit=self._refine_limit,
        )
        return self._to_result(
            query, project, selected,
            parsed.keywords, parsed.topic, parsed, campaign_id,
            start, len(selected),
        )

    def search_project(
        self,
        project_id: str,
        query: str,
        top_n: int | None = None,
        include_history: bool = False,
    ) -> RetrievalResult:
        """Поиск в рамках проекта (проект обязателен)."""
        return self.search(
            query, project_id=project_id, top_n=top_n,
            include_history=include_history,
        )

    def search_campaign(
        self,
        project_id: str,
        campaign_id: str,
        query: str,
        top_n: int | None = None,
        include_history: bool = False,
    ) -> RetrievalResult:
        """Поиск в рамках кампании (проект + кампания обязательны)."""
        return self.search(
            query, project_id=project_id, campaign_id=campaign_id,
            top_n=top_n, include_history=include_history,
        )

    def related(
        self,
        project_id: str,
        knowledge_id: str,
        top_n: int | None = None,
        depth: int | None = None,
    ) -> RetrievalResult:
        """Связанные знания (только Q4 + RepositoryManager по UUID)."""
        self._retrieval_count += 1
        start = time.monotonic()
        entity = self._repositories.knowledge.load(project_id, knowledge_id)
        if entity is None:
            raise RetrievalError(f"Knowledge not found: {knowledge_id}")
        seed = RankedCandidate(
            entity=entity,
            entity_type="knowledge",
            score=float(entity.confidence),
            factors={"confidence": float(entity.confidence) / 100.0},
        )
        snapshot = self._query.snapshot(project_id)
        traverser = RelationshipTraverser(
            self._repositories,
            max_depth=depth if depth is not None else self._max_depth,
            max_related=100,
        )
        expanded = traverser.traverse([seed], project_id, snapshot)
        selected = self._retriever._selector.select(
            expanded[1:], top_n if top_n is not None else self._top_n
        )
        return self._to_result(
            f"related:{knowledge_id}", project_id, selected,
            [], "", ParsedQuery(), None, start, len(selected),
        )

    def explain(
        self,
        project_id: str,
        knowledge_id: str,
        query: str | None = None,
    ) -> RetrievalExplanation:
        """Объяснение выбора Knowledge (разложение по факторам).

        Args:
            project_id: UUID проекта.
            knowledge_id: UUID Knowledge.
            query: Запрос (если None — интринсик-качество).

        Returns:
            RetrievalExplanation.

        """
        entity = self._load_knowledge(project_id, knowledge_id)
        from hkos.services.librarian.knowledge_status import KnowledgeStatus

        if query:
            parsed = QueryParser(self._config).parse(query)
            score, factors = self._retriever._ranking.score(
                entity, "knowledge", parsed, project_id, None
            )
        else:
            factors = {
                "confidence": float(entity.confidence) / 100.0,
                "canonical": 1.0 if KnowledgeStatus.is_canonical(entity) else 0.0,
            }
            score = sum(value for value in factors.values()) * 100.0

        return RetrievalExplanation(
            reason=", ".join(
                name for name, value in factors.items() if value > 0.0
            ) or "Intrinsic quality",
            score=score,
            confidence=entity.confidence,
            canonical=KnowledgeStatus.is_canonical(entity),
            project_match=True,
        )

    def statistics(self, project_id: str | None = None) -> dict[str, object]:
        """Статистика Retrieval Engine.

        Аддитивный диагностический ключ last_retrieval (DS-009A, задача 3):
        измерения двухфазного ранжирования (candidates/refined/stub) для
        оценки необходимости изменения refine_limit. Публичный API и
        существующие ключи не изменены.
        """
        result: dict[str, object] = {
            "retrieval_count": self._retrieval_count,
        }
        last_stats = self._retriever._ranking.last_stats
        if last_stats:
            result["last_retrieval"] = dict(last_stats)
        if project_id:
            result["project_statistics"] = self._query.statistics(project_id)
        return result

"""HKOS Context Manager (DS-009)
================================
Оркестрация конвейера построения контекста (IP-009, порядок фиксирован):

    RetrievalResult
    -> Snapshot Loader
    -> Canonical Merge (в Optimizer)
    -> Context Optimizer
    -> Token Estimator
    -> Validator
    -> Serializer
    -> Context
"""

from hkos.context.context_optimizer import ContextOptimizer
from hkos.context.context_serializer import ContextSerializer
from hkos.context.context_validator import ContextValidator
from hkos.context.models import ContextDocument, ContextItem
from hkos.context.snapshot_loader import SnapshotLoader
from hkos.context.token_estimator import TokenEstimator
from hkos.retrieval.retrieval_engine import RetrievalResult

__all__ = ["ContextManager"]


class ContextManager:
    """Конвейер Context Builder (Builder -> Snapshot -> Merge -> Optimizer ->
    Estimator -> Validator -> Serializer).
    """

    def __init__(
        self,
        loader: SnapshotLoader,
        optimizer: ContextOptimizer,
        serializer: ContextSerializer,
        validator: ContextValidator,
        estimator: TokenEstimator,
    ) -> None:
        """Инициализация конвейера (стадии инжектируются)."""
        self._loader = loader
        self._optimizer = optimizer
        self._serializer = serializer
        self._validator = validator
        self._estimator = estimator

    @staticmethod
    def _to_items(result: RetrievalResult) -> list[ContextItem]:
        """RetrievalResult -> элементы контекста (источник: retrieval)."""
        items: list[ContextItem] = []
        for item in result.items:
            items.append(
                ContextItem(
                    entity=item.entity,
                    entity_type=item.entity_type,
                    source="retrieval",
                    reason=item.explanation.reason,
                    score=item.explanation.score,
                    relation_path=list(item.explanation.relation_path),
                    matched_topic=item.explanation.matched_topic,
                    matched_keywords=list(item.explanation.matched_keywords),
                )
            )
        return items

    def build(
        self,
        result: RetrievalResult,
        project_id: str,
        campaign_id: str | None = None,
        profile: str = "MEDIUM",
        include_history: bool = False,
    ) -> ContextDocument:
        """Построить контекст из результата Retrieval.

        Args:
            result: RetrievalResult (DS-008).
            project_id: UUID проекта.
            campaign_id: UUID кампании (опционально).
            profile: SMALL/MEDIUM/LARGE/FULL.
            include_history: Включить исторические статусы.

        Returns:
            ContextDocument (оптимизированный, валидированный,
            с оценкой токенов и секциями).

        """
        # 1. RetrievalResult -> элементы
        items = self._to_items(result)

        # 2. Snapshot Loader (read-only, источник известного состояния)
        snapshot = self._loader.load(project_id)

        context = ContextDocument(
            task=result.query,
            project_id=project_id,
            campaign_id=campaign_id or "",
            profile=profile,
            snapshot=snapshot,
            items=items,
        )

        # 3-4. Canonical Merge + Optimizer (dedup/фильтры/бюджет)
        optimized = self._optimizer.optimize(context, include_history)

        # 5. Token Estimator (по сериализованному тексту)
        text = self._serializer.serialize(optimized)
        optimized.estimates = self._estimator.estimate(text)
        optimized.sections = self._serializer.sectionize(optimized)

        # 6. Validator
        optimized.validation = self._validator.validate(optimized)

        return optimized

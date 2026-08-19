"""HKOS Context Builder (DS-009 §4-6, IP-009)
==========================================
Публичный фасад Context Layer.

Публичный API (ровно эти методы):
    build, optimize, serialize, statistics, validate,
    estimate_tokens, explain

Допустимые зависимости: RepositoryManager (не используется напрямую —
через RetrievalResult), RetrievalEngine, SnapshotLoader, Query Contract.

Запрещено: поиск, StorageEngine, IndexStore, JSON, изменение
Repository/Snapshot/RetrievalResult (архитектурные тесты).
"""


from hkos.context.context_manager import ContextManager
from hkos.context.context_optimizer import ContextOptimizer
from hkos.context.context_serializer import ContextSerializer
from hkos.context.context_statistics import ContextStatistics
from hkos.context.context_validator import ContextValidator
from hkos.context.models import ContextDocument, ContextExplanation
from hkos.context.snapshot_loader import SnapshotLoader
from hkos.context.token_estimator import TokenEstimate, TokenEstimator
from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.index.validation import ValidationResult
from hkos.retrieval.retrieval_engine import RetrievalResult

__all__ = ["ContextBuilder"]

PROFILE_SMALL: str = "SMALL"
PROFILE_MEDIUM: str = "MEDIUM"
PROFILE_LARGE: str = "LARGE"
PROFILE_FULL: str = "FULL"

VALID_PROFILES: frozenset[str] = frozenset({
    PROFILE_SMALL, PROFILE_MEDIUM, PROFILE_LARGE, PROFILE_FULL,
})


class ContextBuilder:
    """Публичный фасад Context Builder (7 методов)."""

    def __init__(
        self,
        config: ConfigLoader,
        logger: HKOSLogger,
        loader: SnapshotLoader | None = None,
        manager: ContextManager | None = None,
    ) -> None:
        """Инициализация Context Builder.

        Args:
            config: ConfigLoader (секция context.*).
            logger: HKOSLogger.
            loader: SnapshotLoader (read-only); по умолчанию без снимков.
            manager: ContextManager; создаётся по умолчанию из конфигурации.

        """
        self._config = config
        self._logger = logger

        # Коэффициенты из конфигурации (без захардкоженных чисел)
        cpt = config.get("context.token_estimator.characters_per_token", 4)
        wpt = config.get("context.token_estimator.words_per_token", 1)
        characters_per_token = float(cpt) if isinstance(cpt, (int, float)) else 4.0
        words_per_token = float(wpt) if isinstance(wpt, (int, float)) else 1.0
        self._estimator = TokenEstimator(characters_per_token, words_per_token)

        # Профили (лимиты токенов)
        raw_profiles = config.get("context.profiles", {})
        profile_limits: dict[str, int] = {}
        if isinstance(raw_profiles, dict):
            for name, limit in raw_profiles.items():
                if isinstance(limit, int):
                    profile_limits[str(name)] = limit

        # Секции сериализатора
        raw_sections = config.get("context.serializer.sections", None)
        sections = (
            [str(s) for s in raw_sections]
            if isinstance(raw_sections, list)
            else None
        )

        self._loader = loader if loader is not None else SnapshotLoader()
        body_limit_raw = config.get("context.serializer.body_limit", 200)
        body_limit = int(body_limit_raw) if isinstance(body_limit_raw, int) else 200
        self._serializer = ContextSerializer(sections, body_limit=body_limit)
        self._optimizer = ContextOptimizer(self._estimator, profile_limits)
        self._validator = ContextValidator(self._serializer)
        self._manager = (
            manager
            if manager is not None
            else ContextManager(
                self._loader, self._optimizer, self._serializer,
                self._validator, self._estimator,
            )
        )

    # --- Публичный API ---

    def build(
        self,
        result: RetrievalResult,
        project_id: str,
        campaign_id: str | None = None,
        profile: str = PROFILE_MEDIUM,
        include_history: bool = False,
    ) -> ContextDocument:
        """Построить контекст (полный конвейер).

        Args:
            result: RetrievalResult (DS-008).
            project_id: UUID проекта.
            campaign_id: UUID кампании (опционально).
            profile: SMALL/MEDIUM/LARGE/FULL.
            include_history: Включить исторические статусы.

        Returns:
            ContextDocument.

        """
        self._logger.info("Context Started")
        if profile not in VALID_PROFILES:
            profile = PROFILE_MEDIUM
        context = self._manager.build(
            result, project_id, campaign_id, profile, include_history
        )
        self._logger.info("Snapshot Loaded")
        self._logger.info("Knowledge Added")
        self._logger.info("Knowledge Removed")
        self._logger.info("Optimization Completed")
        self._logger.info("Serialization Completed")
        self._logger.info("Context Delivered")
        return context

    def optimize(
        self, context: ContextDocument, include_history: bool = False
    ) -> ContextDocument:
        """Оптимизировать контекст (dedup/фильтры/canonical merge/бюджет)."""
        return self._optimizer.optimize(context, include_history)

    def serialize(self, context: ContextDocument) -> str:
        """Сериализовать контекст (стабильный порядок секций)."""
        return self._serializer.serialize(context)

    def statistics(self, context: ContextDocument) -> dict[str, object]:
        """Статистика контекста."""
        return ContextStatistics.calculate(context)

    def validate(self, context: ContextDocument) -> ValidationResult:
        """Проверить документ контекста."""
        return self._validator.validate(context)

    def estimate_tokens(self, text: str) -> TokenEstimate:
        """Оценить размер текста (Characters/Words/Estimated Tokens)."""
        return self._estimator.estimate(text)

    def explain(self, context: ContextDocument) -> list[ContextExplanation]:
        """Объяснение каждого элемента (почему включён/исключён,
        источник, экономия токенов).
        """
        explanations: list[ContextExplanation] = []
        for item in context.items:
            explanations.append(
                ContextExplanation(
                    entity_id=getattr(item.entity, "id", ""),
                    why_included=(
                        f"{item.reason} (source={item.source}, "
                        f"score={item.score:.2f})"
                    ),
                    why_excluded="",
                    source=item.source,
                    token_savings=0,
                )
            )
        for item in context.excluded:
            text = str(
                getattr(item.entity, "title", "")
                or getattr(item.entity, "name", "")
                or ""
            )
            explanations.append(
                ContextExplanation(
                    entity_id=getattr(item.entity, "id", ""),
                    why_included="",
                    why_excluded=item.excluded_reason,
                    source=item.source,
                    token_savings=self._estimator.estimate(text).estimated_tokens,
                )
            )
        return explanations

    @property
    def loader(self) -> SnapshotLoader:
        """SnapshotLoader (read-only)."""
        return self._loader

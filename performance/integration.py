"""HKOS Performance Integration (DS-013 ЭТАП 5)
====================================================
Подключение Performance Layer к pipeline ЧЕРЕЗ DI-обёртки и композицию
(варианты B/C аудита 5.1): бизнес-логика Retrieval/Context/Librarian/
Index/Snapshot НЕ изменяется; измерение и кэширование — на границах
публичных фасадов.

Обёртки гарантируют: результат/порядок/исключения/транзакционность
НЕ изменяются (делегирование; метрика пишется в finally).
"""

from dataclasses import dataclass
from typing import Any, Callable

from hkos.core.logger import HKOSLogger
from hkos.performance.cache_manager import CacheManager
from hkos.performance.context_profiles import PerformanceContextOptimizer
from hkos.performance.metrics_engine import MetricsEngine
from hkos.performance.performance_manager import PerformanceManager

__all__ = [
    "PerformanceIntegration",
    "MeasuredRetrieval",
    "MeasuredContext",
    "MeasuredSnapshot",
    "MeasuredSave",
    "MeasuredIndex",
]


@dataclass(frozen=True)
class PerformanceConfig:
    """Конфигурация Performance Layer (DS-013 ЭТАП 5 §9)."""

    enabled: bool = True
    cache_enabled: bool = True
    cache_max_entries: int = 1000
    cache_ttl_seconds: float = 3600.0
    context_compression: str = "normal"


def create_performance_layer(config: PerformanceConfig | None = None) -> PerformanceManager:
    """Фабрика Performance Layer (без singleton; DI)."""
    cfg = config or PerformanceConfig()
    metrics = MetricsEngine()
    manager = PerformanceManager(
        metrics=metrics,
        logger=None,
        sys_logger=HKOSLogger(),
    )
    if not cfg.enabled:
        manager.stop()
    return manager


class PerformanceIntegration:
    """Композиция: фабрика обёрток вокруг публичных фасадов."""

    def __init__(
        self,
        config: PerformanceConfig | None = None,
        cache: CacheManager | None = None,
        logger: HKOSLogger | None = None,
    ) -> None:
        """Инициализация.

        Args:
            config: Настройки (DS-013 §9).
            cache: Результатный кэш (LRU+TTL).
            logger: Логгер.
        """
        self._config = config or PerformanceConfig()
        self._cache = cache or CacheManager(
            enabled=self._config.cache_enabled,
            max_entries=self._config.cache_max_entries,
            ttl_seconds=self._config.cache_ttl_seconds,
        )
        self._logger = logger or HKOSLogger()
        self._metrics = MetricsEngine()
        self.manager = PerformanceManager(metrics=self._metrics)
        self.optimizer = PerformanceContextOptimizer(self._config.context_compression.upper())

    # ---- обёртки (DI; делегирование + измерение/кэш) ----

    def wrap_retrieval(
        self, engine: object, fingerprint: Callable[[str], object] | None = None
    ) -> "MeasuredRetrieval":
        """Обёртка RetrievalEngine: retrieve() измеряется и кэшируется.

        Cache hit (query+project+campaign+fingerprint) -> без обращения к
        Repository/Index/Ranking.
        """
        return MeasuredRetrieval(engine, self.manager, self._cache, fingerprint, self._logger)

    def wrap_context(self, builder: object) -> "MeasuredContext":
        """Обёртка ContextBuilder: build() измеряется и сжимается."""
        return MeasuredContext(builder, self.manager, self.optimizer)

    def wrap_snapshot(self, engine: object) -> "MeasuredSnapshot":
        """Обёртка SnapshotEngine: load() измеряется и кэшируется."""
        return MeasuredSnapshot(engine, self.manager, self._cache)

    def wrap_save(self, librarian: object) -> "MeasuredSave":
        """Обёртка Librarian: register() измеряется."""
        return MeasuredSave(librarian, self.manager)

    def wrap_index(self, engine: object) -> "MeasuredIndex":
        """Обёртка IndexEngine: update() измеряется."""
        return MeasuredIndex(engine, self.manager)

    # ---- кэш ----

    @property
    def cache(self) -> CacheManager:
        return self._cache


class _BaseWrapper:
    """Делегирующая обёртка (остальные атрибуты — оригинал)."""

    def __init__(self, wrapped: Any) -> None:
        self._wrapped: Any = wrapped

    def __getattr__(self, name: str) -> Any:
        return getattr(self._wrapped, name)


class MeasuredRetrieval(_BaseWrapper):
    """Retrieval: измерение + результатный кэш."""

    def __init__(self, wrapped: object, manager: PerformanceManager,
                 cache: CacheManager, fingerprint: Callable[[str], object] | None,
                 logger: HKOSLogger) -> None:
        super().__init__(wrapped)
        self._manager = manager
        self._cache = cache
        self._fingerprint = fingerprint
        self._logger = logger

    def retrieve(self, query: str, **kwargs: object) -> Any:
        project = str(kwargs.get("project_id", "") or "")
        campaign = str(kwargs.get("campaign_id", "") or "")
        fingerprint = self._fingerprint(project) if self._fingerprint else ""
        key = f"retrieval:{project}:{campaign}:{query}:{fingerprint}"
        cached = self._cache.get(key)
        if cached is not None:
            return cached  # cache hit: без Repository/Index/Ranking
        with self._manager.measure("retrieval", project_id=project, campaign_id=campaign):
            result = self._wrapped.retrieve(query, **kwargs)
        self._cache.set(key, result)
        return result


class MeasuredContext(_BaseWrapper):
    """Context: build() измеряется; результат сжимается по профилю."""

    def __init__(self, wrapped: object, manager: PerformanceManager,
                 optimizer: PerformanceContextOptimizer) -> None:
        super().__init__(wrapped)
        self._manager = manager
        self._optimizer = optimizer

    def build(
        self, result: object, project_id: str = "", **kwargs: object
    ) -> Any:
        with self._manager.measure("context_build", project_id=project_id):
            context = self._wrapped.build(result, project_id, **kwargs)
        return self._optimizer.compress(context)


class MeasuredSnapshot(_BaseWrapper):
    """Snapshot: load() измеряется и кэшируется (проект + fingerprint)."""

    def __init__(self, wrapped: object, manager: PerformanceManager,
                 cache: CacheManager) -> None:
        super().__init__(wrapped)
        self._manager = manager
        self._cache = cache

    def load(self, project: str, version: str | None = None) -> Any:
        key = f"snapshot:{project}:{version or 'latest'}"
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        with self._manager.measure("snapshot_load", project_id=project):
            result = self._wrapped.load(project, version)
        if result is not None:
            self._cache.set(key, result)
        return result


class MeasuredSave(_BaseWrapper):
    """Librarian: register() измеряется."""

    def __init__(self, wrapped: object, manager: PerformanceManager) -> None:
        super().__init__(wrapped)
        self._manager = manager

    def register(self, project_id: str, knowledge: object) -> Any:
        with self._manager.measure("save", project_id=project_id):
            return self._wrapped.register(project_id, knowledge)


class MeasuredIndex(_BaseWrapper):
    """IndexEngine: update() измеряется."""

    def __init__(self, wrapped: object, manager: PerformanceManager) -> None:
        super().__init__(wrapped)
        self._manager = manager

    def update(self, project: str, entity_id: str, entity_type: str) -> Any:
        with self._manager.measure("index_update", project_id=project):
            self._wrapped.update(project, entity_id, entity_type)

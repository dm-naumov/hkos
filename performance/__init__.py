"""HKOS Performance Layer (DS-013 ЭТАП 4)
==========================================
Измерение, статистика, профилирование, наблюдаемость — БЕЗ изменения
инженерной логики HKOS.

- НЕ хранит знания; НЕ изменяет данные/pipeline/результаты;
- не имеет доступа к Repository storage / Migration internals;
- интеграция — только через DI (подключение к сервисам — отдельный этап).
"""

from hkos.performance.cache_manager import CacheManager
from hkos.performance.context_profiles import (
    PROFILE_AGGRESSIVE,
    PROFILE_LIGHT,
    PROFILE_NONE,
    PROFILE_NORMAL,
    PerformanceContextOptimizer,
)
from hkos.performance.exceptions import PerformanceError
from hkos.performance.integration import (
    MeasuredContext,
    MeasuredIndex,
    MeasuredRetrieval,
    MeasuredSave,
    MeasuredSnapshot,
    PerformanceConfig,
    PerformanceIntegration,
    create_performance_layer,
)
from hkos.performance.latency_tracker import LatencyTracker
from hkos.performance.metrics_engine import Metric, MetricsEngine
from hkos.performance.performance_manager import (
    EVENT_METRIC_RECORDED,
    EVENT_PROFILING_FINISHED,
    EVENT_PROFILING_STARTED,
    EVENT_RESOURCE_WARNING,
    PerformanceLogger,
    PerformanceManager,
)
from hkos.performance.profiler import Profiler
from hkos.performance.resource_monitor import ResourceMonitor

__all__ = [
    "PerformanceManager",
    "PerformanceLogger",
    "MetricsEngine",
    "Metric",
    "Profiler",
    "LatencyTracker",
    "ResourceMonitor",
    "PerformanceError",
    "EVENT_PROFILING_STARTED",
    "EVENT_PROFILING_FINISHED",
    "EVENT_METRIC_RECORDED",
    "EVENT_RESOURCE_WARNING",
    "CacheManager",
    "PerformanceContextOptimizer",
    "PROFILE_NONE",
    "PROFILE_LIGHT",
    "PROFILE_NORMAL",
    "PROFILE_AGGRESSIVE",
    "PerformanceConfig",
    "PerformanceIntegration",
    "create_performance_layer",
    "MeasuredRetrieval",
    "MeasuredContext",
    "MeasuredSnapshot",
    "MeasuredSave",
    "MeasuredIndex",
]

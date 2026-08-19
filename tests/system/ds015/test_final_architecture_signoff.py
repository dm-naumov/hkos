"""DS-015 ЭТАП 5.1: Final Architecture Sign-off.
================================================================
A) Dependency integrity  B) Public API integrity  C) DS-013 compatibility.
"""

import inspect
import os
from pathlib import Path

from hkos.performance.cache_manager import CacheManager
from hkos.performance.context_profiles import PerformanceContextOptimizer
from hkos.performance.metrics_engine import MetricsEngine


class TestFinalArchitectureSignoff:
    """Финальный архитектурный sign-off."""

    def test_a_dependency_integrity(self) -> None:
        """Импорты соответствуют слоям; нет запрещённых зависимостей."""
        # performance импортирует ТОЛЬКО core (измерительный слой)
        for module_name in ("performance.performance_manager",
                            "performance.metrics_engine",
                            "performance.cache_manager",
                            "performance.profiler",
                            "performance.latency_tracker",
                            "performance.resource_monitor"):
            module = __import__(f"hkos.{module_name}", fromlist=["x"])
            source = inspect.getsource(module)
            for forbidden in ("repository", "retrieval", "context",
                              "snapshot", "migration", "librarian"):
                assert f"hkos.{forbidden}" not in source, (
                    f"{module_name}: imports hkos.{forbidden}")
        # migration не импортируется бизнес-слоями (обслуживающий верхний)
        layers = ["repository", "retrieval", "context", "snapshot", "services"]
        repo_root = Path(__file__).resolve().parents[3]
        for layer in layers:
            d = str(repo_root / layer)
            for root, _dirs, files in os.walk(d):
                for name in files:
                    if not name.endswith(".py"):
                        continue
                    source = open(os.path.join(root, name), encoding="utf-8").read()
                    assert "hkos.migration" not in source, (
                        f"{layer}/{name}: imports hkos.migration")

    def test_b_public_api_integrity(self) -> None:
        """Публичные API доступны; сигнатуры не изменились."""
        from hkos.migration.migration_engine import MigrationEngine
        from hkos.retrieval import RetrievalEngine

        # MigrationEngine: ровно 7 методов + 2 lock-helper (DS-011 §6)
        methods = {n for n in vars(MigrationEngine)
                   if not n.startswith("_") and callable(getattr(MigrationEngine, n))}
        assert methods == {"detect", "migrate", "rollback", "validate",
                           "backup", "history", "status",
                           "acquire_lock", "release_lock"}
        # RetrievalEngine.retrieve сигнатура (DS-008)
        signature = inspect.signature(RetrievalEngine.retrieve)
        params = list(signature.parameters)
        assert params[:3] == ["self", "query", "project_id"]

    def test_c_ds013_compatibility(self) -> None:
        """CacheManager bounded; TTL/LRU; MetricsEngine не влияет; protected."""
        cache = CacheManager(max_entries=2, ttl_seconds=100)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        assert cache.get("a") is None  # LRU
        assert cache.statistics()["size"] <= 2  # bounded
        metrics = MetricsEngine()
        metrics.record("retrieval", 1.5)
        assert metrics.entries()[0].duration_ms == 1.5  # только измерение
        # TokenOptimizer сохраняет protected (семантика DS-013)
        optimizer = PerformanceContextOptimizer("AGGRESSIVE")
        from hkos.context.models import ContextDocument, ContextItem
        from hkos.repository.models import Knowledge
        context = ContextDocument(items=[
            ContextItem(entity=Knowledge(title="D udp", body="x",
                                         category="DECISION"),
                        entity_type="knowledge"),
            ContextItem(entity=Knowledge(title="T udp", body="y"),
                        entity_type="knowledge"),
        ], project_id="p1")
        compressed = optimizer.compress(context)
        assert compressed.sections.get("DECISIONS"), "protected lost"

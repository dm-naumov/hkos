"""DS-015 ЭТАП 3: Release Candidate Validation.
================================================================
Артефакты релиза: версия, production config, миграционные скрипты,
документация; метрики корректны (нет отрицательных/NaN); логи создаются.
"""

import math
from pathlib import Path

import yaml

from hkos.performance.performance_manager import PerformanceManager
from hkos.repository.models import Knowledge
from tests.system.ds015.fixtures import create_ds015_context

_REPO = Path(__file__).resolve().parents[3]
CONFIG_PROD = _REPO / "config" / "hkos-production.yaml"


class TestReleaseCandidate:
    """Готовность релиза 1.0."""

    def test_version_and_config(self) -> None:
        config = yaml.safe_load(CONFIG_PROD.read_text())
        version = config["hkos"]["version"]
        assert version.startswith("1.0"), f"version {version}"
        assert config["hkos"]["enabled"] is True

    def test_migration_scripts_available(self) -> None:
        """Миграционные компоненты DS-011 доступны."""
        from hkos.migration import (
            MigrationEngine,
            MigrationRegistry,
            MigrationStep,
            SchemaDetector,
            VersionManifest,
        )
        assert MigrationEngine is not None
        assert MigrationRegistry is not None
        assert MigrationStep is not None
        assert SchemaDetector is not None
        assert VersionManifest is not None

    def test_documentation_synced(self) -> None:
        docs = _REPO / "docs"
        required = [
            "architecture.md", "installation.md", "administrator.md",
            "developer.md", "api-reference.md", "migration-guide.md",
            "troubleshooting.md", "performance-guide.md",
        ]
        for name in required:
            assert (docs / name).exists()

    def test_metrics_correct(self) -> None:
        """Метрики собираются; нет отрицательных значений/NaN."""
        manager = PerformanceManager()
        with manager.measure("retrieval"):
            pass
        with manager.measure("retrieval"):
            pass
        stats = manager.statistics().get("metrics")
        assert isinstance(stats, list) and stats
        for stat in stats:
            assert stat.count >= 1
            assert stat.average_ms >= 0
            assert stat.min_ms >= 0
            assert stat.max_ms >= 0
            assert not math.isnan(stat.average_ms)

    def test_logging_files_created(self, tmp_path: Path) -> None:
        """Журналы создаются; события записываются; rotation настроен."""
        from hkos.performance.performance_manager import PerformanceLogger

        logger = PerformanceLogger(tmp_path / "logs" / "performance.log")
        logger.log("PROFILING_STARTED", "performance", "test")
        log_file = tmp_path / "logs" / "performance.log"
        assert log_file.exists()
        assert "PROFILING_STARTED" in log_file.read_text()
        config = yaml.safe_load(CONFIG_PROD.read_text())
        assert config["logging"]["max_size_mb"] > 0
        assert config["logging"]["backup_count"] > 0

    def test_metrics_validation(self, tmp_path: Path) -> None:
        """Production-метрики: Repository/Knowledge/Project/Campaign/Index."""
        ctx = create_ds015_context(tmp_path)
        project = ctx.project.create(name="Metrics", tags=["m"])
        for i in range(5):
            ctx.librarian.register(project.id, Knowledge(
                title=f"M{i}fact udp", body="udp", tags=["udp"]))
        ctx.index.build(project.id)
        metrics = {
            "repository_size": ctx.repos.knowledge.count(project.id),
            "knowledge_count": ctx.repos.knowledge.count(project.id),
            "project_count": len(ctx.project.list()),
            "campaign_count": len(ctx.campaign.list(project.id)),
            "index_size": int(ctx.index.statistics(project.id).get("knowledge", 0)),
        }
        for name, value in metrics.items():
            assert value >= 0, f"{name} negative"
        assert metrics["knowledge_count"] == 5
        assert metrics["index_size"] == 5

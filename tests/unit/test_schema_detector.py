"""Unit tests: SchemaDetector (DS-011 §11)."""

import pytest

from hkos.migration.exceptions import MigrationError
from hkos.migration.migration_registry import MigrationRegistry, MigrationStep
from hkos.migration.schema_detector import SchemaDetector


def _registry() -> MigrationRegistry:
    registry = MigrationRegistry()
    registry.register(MigrationStep("001", 1, 2))
    registry.register(MigrationStep("002", 2, 3))
    return registry


class TestSchemaDetector:
    """Детерминированное детектирование версии (только конверты)."""

    def test_current_min_version(self) -> None:
        detector = SchemaDetector(_registry(), lambda pid: [1, 1, 1])
        info = detector.detect(["p1"])
        assert info.current_version == 1
        assert info.target_version == 3
        assert info.pending == ["001", "002"]
        assert info.mixed is False

    def test_mixed_detection(self) -> None:
        detector = SchemaDetector(_registry(), lambda pid: [1, 2, 2])
        info = detector.detect(["p1"])
        assert info.mixed is True
        assert info.current_version == 1  # минимум (догоняющая миграция)

    def test_already_updated_no_pending(self) -> None:
        detector = SchemaDetector(_registry(), lambda pid: [3, 3])
        info = detector.detect(["p1"])
        assert info.current_version == 3
        assert info.target_version == 3
        assert info.pending == []
        assert info.mixed is False

    def test_unknown_future_version_aborts(self) -> None:
        detector = SchemaDetector(_registry(), lambda pid: [4])
        with pytest.raises(MigrationError):
            detector.detect(["p1"])

    def test_legacy_missing_version_is_one(self) -> None:
        """Отсутствие version -> legacy (v1); порт маппит в 1 (§11)."""
        detector = SchemaDetector(_registry(), lambda pid: [1])  # legacy-документы
        info = detector.detect(["p1"])
        assert info.current_version == 1
        assert info.pending == ["001", "002"]

    def test_empty_projects(self) -> None:
        """Нет документов -> current == target (мигрировать нечего)."""
        detector = SchemaDetector(_registry(), lambda pid: [])
        info = detector.detect(["p1", "p2"])
        assert info.current_version == 3
        assert info.target_version == 3
        assert info.pending == []

    def test_empty_registry(self) -> None:
        detector = SchemaDetector(MigrationRegistry(), lambda pid: [1])
        info = detector.detect(["p1"])
        assert info.target_version == 1  # пустой реестр -> целевая 1
        assert info.pending == []

    def test_deterministic(self) -> None:
        """Одинаковый вход -> одинаковый результат."""
        detector = SchemaDetector(_registry(), lambda pid: [1, 2])
        first = detector.detect(["p1", "p2"])
        second = detector.detect(["p1", "p2"])
        assert first == second

    def test_multi_project_aggregation(self) -> None:
        detector = SchemaDetector(_registry(), lambda pid: [1] if pid == "p1" else [3])
        info = detector.detect(["p1", "p2"])
        assert info.mixed is True
        assert info.current_version == 1

    def test_target_is_last_registered(self) -> None:
        registry = MigrationRegistry()
        registry.register(MigrationStep("001", 1, 2))
        detector = SchemaDetector(registry, lambda pid: [1])
        info = detector.detect(["p1"])
        assert info.target_version == 2

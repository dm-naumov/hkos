"""Unit tests for ConfidenceEngine (DS-006 §14, IP-006 §7, §15)."""

from hkos.repository.models import Knowledge
from hkos.services.librarian.confidence_engine import (
    CONFIDENCE_MAX,
    CONFIDENCE_MIN,
    ConfidenceEngine,
)


class TestConfidenceEngine:
    """Confidence вычисляется детерминированно; не хранится вручную."""

    def test_base_confidence(self) -> None:
        assert ConfidenceEngine.calculate(Knowledge(id="1")) == 50

    def test_confirmations_increase(self) -> None:
        k = Knowledge(id="1", confirmations=2)
        assert ConfidenceEngine.calculate(k) == 60

    def test_independent_campaigns(self) -> None:
        k = Knowledge(id="1", independent_campaigns=3)
        assert ConfidenceEngine.calculate(k) == 80

    def test_successful_usage(self) -> None:
        k = Knowledge(id="1", successful_usage=4)
        assert ConfidenceEngine.calculate(k) == 70

    def test_failed_usage_decreases(self) -> None:
        k = Knowledge(id="1", failed_usage=2)
        assert ConfidenceEngine.calculate(k) == 30

    def test_conflicts_decrease(self) -> None:
        k = Knowledge(id="1", conflicts=3)
        assert ConfidenceEngine.calculate(k) == 20  # 50 - min(45, cap 30)

    def test_clamped_to_max(self) -> None:
        k = Knowledge(id="1", confirmations=100, independent_campaigns=100,
                      successful_usage=100)
        assert ConfidenceEngine.calculate(k) == CONFIDENCE_MAX

    def test_clamped_to_min(self) -> None:
        k = Knowledge(id="1", failed_usage=100, conflicts=100)
        assert ConfidenceEngine.calculate(k) == CONFIDENCE_MIN

    def test_deterministic(self) -> None:
        k = Knowledge(id="1", confirmations=3, independent_campaigns=2,
                      successful_usage=1, failed_usage=1, conflicts=1)
        first = ConfidenceEngine.calculate(k)
        second = ConfidenceEngine.calculate(Knowledge(
            id="2", confirmations=3, independent_campaigns=2,
            successful_usage=1, failed_usage=1, conflicts=1,
        ))
        assert first == second

    def test_independent_of_text_and_date(self) -> None:
        a = Knowledge(id="1", title="x" * 500, body="y" * 5000,
                      created_at="2026-01-01T00:00:00+00:00")
        b = Knowledge(id="2", title="short", body="",
                      created_at="2025-01-01T00:00:00+00:00")
        assert ConfidenceEngine.calculate(a) == ConfidenceEngine.calculate(b)

    def test_no_manual_increment_api(self) -> None:
        """Нет add/increment; только calculate + управление стратегией."""
        public = [m for m in dir(ConfidenceEngine) if not m.startswith("_")]
        assert set(public) <= {"calculate", "strategy", "set_strategy"}

"""Unit tests for Confidence Strategy Pattern (DS-006A §5)."""

from hkos.repository.models import Knowledge
from hkos.services.librarian.confidence_engine import (
    ConfidenceEngine,
    ConfidenceStrategy,
    LinearConfidenceStrategy,
)


class DummyStrategy:
    """Тестовая стратегия (замена для проверки Pattern)."""

    def calculate(self, knowledge: Knowledge) -> int:
        return 42


class TestConfidenceStrategy:
    """Strategy Pattern: интерфейс + замена стратегии."""

    def test_linear_strategy_implements_interface(self) -> None:
        assert isinstance(LinearConfidenceStrategy(), ConfidenceStrategy)

    def test_linear_strategy_formula(self) -> None:
        k = Knowledge(id="1", confirmations=2)
        assert LinearConfidenceStrategy().calculate(k) == 60

    def test_default_strategy_is_linear(self) -> None:
        assert isinstance(ConfidenceEngine.strategy(), LinearConfidenceStrategy)

    def test_static_calculate_backward_compatible(self) -> None:
        """ConfidenceEngine.calculate(knowledge) — прежнее поведение."""
        k = Knowledge(id="1", confirmations=4)
        assert ConfidenceEngine.calculate(k) == 70

    def test_strategy_swappable(self) -> None:
        ConfidenceEngine.set_strategy(DummyStrategy())
        try:
            assert ConfidenceEngine.calculate(Knowledge(id="1")) == 42
            assert isinstance(ConfidenceEngine.strategy(), DummyStrategy)
        finally:
            ConfidenceEngine.set_strategy(LinearConfidenceStrategy())

    def test_strategy_restored(self) -> None:
        assert isinstance(ConfidenceEngine.strategy(), LinearConfidenceStrategy)

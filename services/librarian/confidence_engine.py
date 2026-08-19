"""HKOS Confidence Engine (DS-006 §14, IP-006 §7, §15, DS-006A §5)
================================================================
Confidence вычисляется, никогда не хранится вручную и не редактируется.

Architecture (DS-006A §5): Strategy Pattern.
    ConfidenceStrategy — внутренний интерфейс;
    LinearConfidenceStrategy — единственная текущая реализация
    (формула не изменена).

Цель: в DS-009 замена стратегии без изменения Librarian.

Формула детерминированная, зависит ТОЛЬКО от инженерных факторов
(IP-006 §15): confirmations, independent_campaigns, successful_usage,
failed_usage, conflicts. НЕ зависит от длины текста, автора, даты.

    base = 50
    + confirmations * 5          (max +30)
    + independent_campaigns * 10 (max +30)
    + successful_usage * 5       (max +20)
    - failed_usage * 10          (max -40)
    - conflicts * 15             (max -30)
    clamp 0..100

Допускается только calculate(). Прямое инкрементальное
изменение confidence в обход расчёта запрещено.
"""

from typing import Final, Protocol, runtime_checkable

from hkos.repository.models import Knowledge

__all__ = [
    "ConfidenceStrategy",
    "LinearConfidenceStrategy",
    "ConfidenceEngine",
]

CONFIDENCE_MIN: Final[int] = 0
CONFIDENCE_MAX: Final[int] = 100
CONFIDENCE_BASE: Final[int] = 50

_CONFIRMATION_STEP: Final[int] = 5
_CONFIRMATION_CAP: Final[int] = 30
_CAMPAIGN_STEP: Final[int] = 10
_CAMPAIGN_CAP: Final[int] = 30
_SUCCESS_STEP: Final[int] = 5
_SUCCESS_CAP: Final[int] = 20
_FAILURE_STEP: Final[int] = 10
_FAILURE_CAP: Final[int] = 40
_CONFLICT_STEP: Final[int] = 15
_CONFLICT_CAP: Final[int] = 30


@runtime_checkable
class ConfidenceStrategy(Protocol):
    """Внутренний интерфейс стратегии расчёта confidence (DS-006A §5)."""

    def calculate(self, knowledge: Knowledge) -> int:
        """Вычислить confidence (0..100)."""
        ...


class LinearConfidenceStrategy:
    """Линейная стратегия (единственная текущая реализация).

    Формула не изменена по сравнению с DS-006.
    """

    def calculate(self, knowledge: Knowledge) -> int:
        """Вычислить confidence (0..100) из инженерных факторов.

        Args:
            knowledge: Знание с заполненными факторами.

        Returns:
            Целое значение confidence в диапазоне 0..100.
        """
        score = CONFIDENCE_BASE
        score += min(
            knowledge.confirmations * _CONFIRMATION_STEP, _CONFIRMATION_CAP
        )
        score += min(
            knowledge.independent_campaigns * _CAMPAIGN_STEP, _CAMPAIGN_CAP
        )
        score += min(
            knowledge.successful_usage * _SUCCESS_STEP, _SUCCESS_CAP
        )
        score -= min(
            knowledge.failed_usage * _FAILURE_STEP, _FAILURE_CAP
        )
        score -= min(knowledge.conflicts * _CONFLICT_STEP, _CONFLICT_CAP)
        return max(CONFIDENCE_MIN, min(CONFIDENCE_MAX, score))


class ConfidenceEngine:
    """Фасад расчёта confidence (Strategy Pattern).

    Использует LinearConfidenceStrategy по умолчанию.
    Для DS-009 стратегия может быть заменена через set_strategy()
    без изменения Librarian.

    Обратная совместимость: ConfidenceEngine.calculate(knowledge)
    продолжает работать (classmethod-диспетчеризация).
    """

    _strategy: ConfidenceStrategy = LinearConfidenceStrategy()

    @classmethod
    def strategy(cls) -> ConfidenceStrategy:
        """Текущая стратегия."""
        return cls._strategy

    @classmethod
    def set_strategy(cls, strategy: ConfidenceStrategy) -> None:
        """Заменить стратегию (для DS-009).

        Args:
            strategy: Реализация ConfidenceStrategy.
        """
        cls._strategy = strategy

    @classmethod
    def calculate(cls, knowledge: Knowledge) -> int:
        """Вычислить confidence через текущую стратегию."""
        return cls._strategy.calculate(knowledge)

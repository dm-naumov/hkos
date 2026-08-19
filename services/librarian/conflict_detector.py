"""HKOS Conflict Detector (DS-006 §11, IP-006 §5)
===============================================
Отвечает ТОЛЬКО на вопрос «есть ли конфликт?» (YES/NO)
и оценивает confidence конфликта.

НЕ принимает бизнес-решений: не удаляет, не архивирует, не отклоняет,
не изменяет статусы (IP-006 §5).

Детерминированные правила (структурные, без семантики):
- конфликт = тот же нормализованный title и противоположная полярность
  (kind negative/positive или категория FAILURE vs FACT/SUCCESS);
- "более новая версия": тот же title, другой id, создан позже.

Работает только с набором, переданным Librarian.
"""

from dataclasses import dataclass, field

from hkos.repository.models import Knowledge
from hkos.services.librarian.canonicalizer import Canonicalizer
from hkos.services.librarian.knowledge_classifier import (
    CATEGORY_CONFIGURATION,
    CATEGORY_FACT,
    CATEGORY_FAILURE,
    CATEGORY_PATTERN,
    CATEGORY_RULE,
    CATEGORY_SUCCESS,
)

__all__ = ["ConflictResult", "ConflictDetector"]

# Категории "положительной" полярности (противоположны FAILURE).
_POSITIVE_CATEGORIES: frozenset[str] = frozenset({
    CATEGORY_FACT, CATEGORY_SUCCESS, CATEGORY_RULE, CATEGORY_PATTERN,
    CATEGORY_CONFIGURATION,
})


@dataclass
class ConflictResult:
    """Результат проверки конфликта (IP-006 §5)."""

    conflict_exists: bool = False
    confidence_of_conflict: float = 0.0
    conflicting: list[Knowledge] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        """Результат как словарь."""
        return {
            "conflict_exists": self.conflict_exists,
            "confidence_of_conflict": self.confidence_of_conflict,
            "conflicting_ids": [k.id for k in self.conflicting],
        }


class ConflictDetector:
    """Детектор конфликтов (только YES/NO + confidence)."""

    @staticmethod
    def _is_negative(knowledge: Knowledge) -> bool:
        """Отрицательная полярность знания."""
        if knowledge.kind == "negative":
            return True
        return knowledge.category == CATEGORY_FAILURE

    @classmethod
    def detect(
        cls,
        candidate: Knowledge,
        candidates: list[Knowledge],
    ) -> ConflictResult:
        """Проверить наличие конфликта candidate с candidates.

        Args:
            candidate: Проверяемое знание.
            candidates: Набор для сравнения (передаёт Librarian).

        Returns:
            ConflictResult: conflict_exists, confidence_of_conflict,
            список конфликтующих Knowledge.
        """
        target = Canonicalizer.normalize(candidate.title)
        if not target:
            return ConflictResult()

        candidate_negative = cls._is_negative(candidate)
        conflicting: list[Knowledge] = []
        for other in candidates:
            if other.id == candidate.id:
                continue
            if Canonicalizer.normalize(other.title) != target:
                continue
            other_negative = cls._is_negative(other)
            # Противоположная полярность -> конфликт.
            if candidate_negative != other_negative:
                conflicting.append(other)
            # Более новая версия того же утверждения -> потенциальный
            # конфликт версий (supersede), если даты различимы.
            elif other.created_at and candidate.created_at:
                if other.created_at > candidate.created_at:
                    conflicting.append(other)

        if not conflicting:
            return ConflictResult()
        return ConflictResult(
            conflict_exists=True,
            confidence_of_conflict=1.0,
            conflicting=conflicting,
        )

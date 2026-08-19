"""HKOS Knowledge Classifier (DS-006 §8, IP-006 §2)
================================================
Определяет категорию нового Knowledge.

Категории (только эти): FACT, HYPOTHESIS, DECISION, RULE, PATTERN,
FAILURE, SUCCESS, WORKAROUND, CONFIGURATION, REFERENCE.

Классификация детерминированная (ключевые слова, без семантики):
- kind='negative' -> FAILURE;
- наличие маркеров в title/body -> соответствующая категория;
- по умолчанию FACT.

Категория неизменяема после канонизации (DS-006 §8).
"""

from typing import Final

from hkos.repository.models import Knowledge

__all__ = [
    "CATEGORY_FACT",
    "CATEGORY_HYPOTHESIS",
    "CATEGORY_DECISION",
    "CATEGORY_RULE",
    "CATEGORY_PATTERN",
    "CATEGORY_FAILURE",
    "CATEGORY_SUCCESS",
    "CATEGORY_WORKAROUND",
    "CATEGORY_CONFIGURATION",
    "CATEGORY_REFERENCE",
    "VALID_CATEGORIES",
    "KnowledgeClassifier",
]

CATEGORY_FACT: Final[str] = "FACT"
CATEGORY_HYPOTHESIS: Final[str] = "HYPOTHESIS"
CATEGORY_DECISION: Final[str] = "DECISION"
CATEGORY_RULE: Final[str] = "RULE"
CATEGORY_PATTERN: Final[str] = "PATTERN"
CATEGORY_FAILURE: Final[str] = "FAILURE"
CATEGORY_SUCCESS: Final[str] = "SUCCESS"
CATEGORY_WORKAROUND: Final[str] = "WORKAROUND"
CATEGORY_CONFIGURATION: Final[str] = "CONFIGURATION"
CATEGORY_REFERENCE: Final[str] = "REFERENCE"

VALID_CATEGORIES: Final[frozenset[str]] = frozenset({
    CATEGORY_FACT,
    CATEGORY_HYPOTHESIS,
    CATEGORY_DECISION,
    CATEGORY_RULE,
    CATEGORY_PATTERN,
    CATEGORY_FAILURE,
    CATEGORY_SUCCESS,
    CATEGORY_WORKAROUND,
    CATEGORY_CONFIGURATION,
    CATEGORY_REFERENCE,
})

# Детерминированные маркеры категорий: (категория, подстроки в lower()).
_CATEGORY_MARKERS: Final[list[tuple[str, tuple[str, ...]]]] = [
    (CATEGORY_FAILURE,
     ("не работает", "fail", "error", "ломает", "отказ", "broken")),
    (CATEGORY_SUCCESS, ("работает", "success", "успешно", "fixed", "решено")),
    (CATEGORY_HYPOTHESIS, ("гипотеза", "hypothesis", "предположим", "возможно")),
    (CATEGORY_DECISION, ("решение", "decision", "выбрали", "принято решение")),
    (CATEGORY_RULE, ("правило", "rule", "всегда", "никогда")),
    (CATEGORY_PATTERN, ("паттерн", "pattern", "шаблон")),
    (CATEGORY_WORKAROUND, ("workaround", "обход", "временное решение")),
    (CATEGORY_CONFIGURATION, ("конфигурация", "config", "настройка")),
    (CATEGORY_REFERENCE, ("ссылка", "reference", "документация", "см.")),
]


class KnowledgeClassifier:
    """Классификатор категорий Knowledge (детерминированный)."""

    @staticmethod
    def classify(knowledge: Knowledge) -> str:
        """Определить категорию Knowledge.

        Args:
            knowledge: Знание (title/body/kind анализируются).

        Returns:
            Категория из VALID_CATEGORIES.
        """
        if knowledge.kind == "negative":
            return CATEGORY_FAILURE
        text = f"{knowledge.title}\n{knowledge.body}".lower()
        for category, markers in _CATEGORY_MARKERS:
            for marker in markers:
                if marker in text:
                    return category
        return CATEGORY_FACT

    @staticmethod
    def is_valid(category: str) -> bool:
        """Проверить, что категория допустима."""
        return category in VALID_CATEGORIES

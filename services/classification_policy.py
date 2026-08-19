"""HKOS Classification Policy (Post-Audit Refinement, единый источник)
======================================================================
Единственный источник правил распределения Knowledge по ЛОГИЧЕСКИМ
категориям. Используется ContextSerializer и SnapshotBuilder — одно
Knowledge всегда получает ОДНУ и ту же логическую категорию независимо
от потребителя (устранены расхождения RULE/PATTERN/VERIFIED/FAILURE/
kind=negative/DECISION — замечания Stability Audit v3.0 и Foundation
Certification v5.0).

Логические категории:
    ARTIFACT, DECISION, CANONICAL, CONFIGURATION, FAILURE,
    LIMITATION, ARCHITECTURE, QUESTION

Правила (приоритет сверху вниз):
    1. entity_type == artifact              -> ARTIFACT
    2. entity_type == decision              -> DECISION
    3. status == CANONICAL                  -> CANONICAL
    4. category == DECISION                 -> DECISION
    5. category == FAILURE или kind=negative-> FAILURE
    6. category in (CONFIGURATION, RULE,
       PATTERN)                             -> CONFIGURATION
    7. status == SUPERSEDED                 -> LIMITATION
    8. status == VERIFIED                   -> ARCHITECTURE
    9. category == FACT                     -> CANONICAL
    10. иначе                               -> QUESTION

Каждый потребитель отображает логическую категорию на свои секции;
сама классификация — единая.
"""

from typing import Final

from hkos.services.librarian.knowledge_classifier import (
    CATEGORY_CONFIGURATION as _K_CATEGORY_CONFIGURATION,
)
from hkos.services.librarian.knowledge_classifier import (
    CATEGORY_DECISION as _K_CATEGORY_DECISION,
)
from hkos.services.librarian.knowledge_classifier import (
    CATEGORY_FACT as _K_CATEGORY_FACT,
)
from hkos.services.librarian.knowledge_classifier import (
    CATEGORY_FAILURE as _K_CATEGORY_FAILURE,
)
from hkos.services.librarian.knowledge_classifier import (
    CATEGORY_PATTERN as _K_CATEGORY_PATTERN,
)
from hkos.services.librarian.knowledge_classifier import (
    CATEGORY_RULE as _K_CATEGORY_RULE,
)
from hkos.services.librarian.knowledge_classifier import (
    VALID_CATEGORIES,
)
from hkos.services.librarian.knowledge_status import (
    KNOWLEDGE_STATUS_CANONICAL,
    KNOWLEDGE_STATUS_SUPERSEDED,
    KNOWLEDGE_STATUS_VERIFIED,
)

__all__ = [
    "CATEGORY_ARTIFACT",
    "CATEGORY_DECISION",
    "CATEGORY_CANONICAL",
    "CATEGORY_CONFIGURATION",
    "CATEGORY_FAILURE",
    "CATEGORY_LIMITATION",
    "CATEGORY_ARCHITECTURE",
    "CATEGORY_QUESTION",
    "classify",
    "is_valid_category",
    "validate_category",
]

CATEGORY_ARTIFACT: Final[str] = "ARTIFACT"
CATEGORY_DECISION: Final[str] = _K_CATEGORY_DECISION
CATEGORY_CANONICAL: Final[str] = "CANONICAL"
CATEGORY_CONFIGURATION: Final[str] = _K_CATEGORY_CONFIGURATION
CATEGORY_FAILURE: Final[str] = _K_CATEGORY_FAILURE
CATEGORY_LIMITATION: Final[str] = "LIMITATION"
CATEGORY_ARCHITECTURE: Final[str] = "ARCHITECTURE"
CATEGORY_RULE: Final[str] = _K_CATEGORY_RULE
CATEGORY_PATTERN: Final[str] = _K_CATEGORY_PATTERN
CATEGORY_FACT: Final[str] = _K_CATEGORY_FACT
CATEGORY_QUESTION: Final[str] = "QUESTION"

_KIND_NEGATIVE: Final[str] = "negative"


def classify(
    entity_type: str,
    category: str,
    kind: str,
    status: str,
) -> str:
    """Логическая категория Knowledge (единая для всех потребителей).

    Args:
        entity_type: Тип сущности ("knowledge"/"decision"/"artifact").
        category: Категория Knowledge (CATEGORY_* из knowledge_classifier).
        kind: kind ("negative" для отрицательных знаний).
        status: Статус Knowledge (KNOWLEDGE_STATUS_*).

    Returns:
        Одна из CATEGORY_* логических категорий.

    """
    if entity_type == "artifact":
        return CATEGORY_ARTIFACT
    if entity_type == "decision":
        return CATEGORY_DECISION
    if status == KNOWLEDGE_STATUS_CANONICAL:
        return CATEGORY_CANONICAL
    if category == CATEGORY_DECISION:
        return CATEGORY_DECISION
    if category == CATEGORY_FAILURE or kind == _KIND_NEGATIVE:
        return CATEGORY_FAILURE
    if category in (CATEGORY_CONFIGURATION, CATEGORY_RULE, CATEGORY_PATTERN):
        return CATEGORY_CONFIGURATION
    if status == KNOWLEDGE_STATUS_SUPERSEDED:
        return CATEGORY_LIMITATION
    if status == KNOWLEDGE_STATUS_VERIFIED:
        return CATEGORY_ARCHITECTURE
    if category == CATEGORY_FACT:
        return CATEGORY_CANONICAL
    return CATEGORY_QUESTION


def is_valid_category(category: str) -> bool:
    """Категория принадлежит замкнутому словарю (CATEGORY_*)."""
    return category in VALID_CATEGORIES


def validate_category(category: str) -> None:
    """Проверить категорию; при недопустимой — ValueError.

    Args:
        category: Категория Knowledge.

    Raises:
        ValueError: категория вне замкнутого словаря.

    """
    if not is_valid_category(category):
        raise ValueError(f"Invalid category: {category!r}")

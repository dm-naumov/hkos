"""HKOS Knowledge Status (DS-006 §9, IP-006 §10)
=============================================
Единственный источник истины о статусах Knowledge и их переходах.

Статусы (только эти): NEW, VERIFIED, CANONICAL, SUPERSEDED,
CONFLICT, REJECTED, ARCHIVED.

Запрещено проверять статусы строками (IP-006 §10):
    if knowledge.status == "VERIFIED"   # ЗАПРЕЩЕНО
Допускается только:
    KnowledgeStatus.is_verified(knowledge)

Любой запрещённый переход -> KnowledgeStatusError.
"""

from typing import Final

from hkos.repository.models import Knowledge
from hkos.services.librarian.exceptions import KnowledgeStatusError

__all__ = [
    "KNOWLEDGE_STATUS_NEW",
    "KNOWLEDGE_STATUS_VERIFIED",
    "KNOWLEDGE_STATUS_CANONICAL",
    "KNOWLEDGE_STATUS_SUPERSEDED",
    "KNOWLEDGE_STATUS_CONFLICT",
    "KNOWLEDGE_STATUS_REJECTED",
    "KNOWLEDGE_STATUS_ARCHIVED",
    "VALID_KNOWLEDGE_STATUSES",
    "TRANSITIONS",
    "KnowledgeStatus",
]

KNOWLEDGE_STATUS_NEW: Final[str] = "NEW"
KNOWLEDGE_STATUS_VERIFIED: Final[str] = "VERIFIED"
KNOWLEDGE_STATUS_CANONICAL: Final[str] = "CANONICAL"
KNOWLEDGE_STATUS_SUPERSEDED: Final[str] = "SUPERSEDED"
KNOWLEDGE_STATUS_CONFLICT: Final[str] = "CONFLICT"
KNOWLEDGE_STATUS_REJECTED: Final[str] = "REJECTED"
KNOWLEDGE_STATUS_ARCHIVED: Final[str] = "ARCHIVED"

VALID_KNOWLEDGE_STATUSES: Final[frozenset[str]] = frozenset({
    KNOWLEDGE_STATUS_NEW,
    KNOWLEDGE_STATUS_VERIFIED,
    KNOWLEDGE_STATUS_CANONICAL,
    KNOWLEDGE_STATUS_SUPERSEDED,
    KNOWLEDGE_STATUS_CONFLICT,
    KNOWLEDGE_STATUS_REJECTED,
    KNOWLEDGE_STATUS_ARCHIVED,
})

# Таблица переходов статусов Knowledge (DS-006 §9 + операции Librarian):
#   NEW -> VERIFIED | CONFLICT | REJECTED | ARCHIVED
#   VERIFIED -> CANONICAL | CONFLICT | ARCHIVED | SUPERSEDED
#   CANONICAL -> SUPERSEDED | ARCHIVED | CONFLICT
#   SUPERSEDED -> ARCHIVED
#   CONFLICT -> VERIFIED | REJECTED | ARCHIVED
#   REJECTED -> ARCHIVED
#   ARCHIVED -> VERIFIED (restore)
TRANSITIONS: Final[dict[str, frozenset[str]]] = {
    KNOWLEDGE_STATUS_NEW: frozenset({
        KNOWLEDGE_STATUS_VERIFIED,
        KNOWLEDGE_STATUS_CONFLICT,
        KNOWLEDGE_STATUS_REJECTED,
        KNOWLEDGE_STATUS_ARCHIVED,
    }),
    KNOWLEDGE_STATUS_VERIFIED: frozenset({
        KNOWLEDGE_STATUS_CANONICAL,
        KNOWLEDGE_STATUS_CONFLICT,
        KNOWLEDGE_STATUS_ARCHIVED,
        KNOWLEDGE_STATUS_SUPERSEDED,
    }),
    KNOWLEDGE_STATUS_CANONICAL: frozenset({
        KNOWLEDGE_STATUS_SUPERSEDED,
        KNOWLEDGE_STATUS_ARCHIVED,
        KNOWLEDGE_STATUS_CONFLICT,
    }),
    KNOWLEDGE_STATUS_SUPERSEDED: frozenset({
        KNOWLEDGE_STATUS_ARCHIVED,
    }),
    KNOWLEDGE_STATUS_CONFLICT: frozenset({
        KNOWLEDGE_STATUS_VERIFIED,
        KNOWLEDGE_STATUS_REJECTED,
        KNOWLEDGE_STATUS_ARCHIVED,
    }),
    KNOWLEDGE_STATUS_REJECTED: frozenset({
        KNOWLEDGE_STATUS_ARCHIVED,
    }),
    KNOWLEDGE_STATUS_ARCHIVED: frozenset({
        KNOWLEDGE_STATUS_VERIFIED,
    }),
}


class KnowledgeStatus:
    """Статус Knowledge: валидация переходов и проверки-предикаты."""

    @staticmethod
    def is_valid(status: str) -> bool:
        """Проверить, что статус допустим."""
        return status in VALID_KNOWLEDGE_STATUSES

    @staticmethod
    def transition(current: str, target: str) -> str:
        """Проверить переход статуса и вернуть целевой.

        Raises:
            KnowledgeStatusError: Если переход запрещён таблицей.
        """
        if current not in VALID_KNOWLEDGE_STATUSES:
            raise KnowledgeStatusError(
                f"Invalid knowledge status: {current!r}; "
                f"allowed: {sorted(VALID_KNOWLEDGE_STATUSES)}"
            )
        if target not in VALID_KNOWLEDGE_STATUSES:
            raise KnowledgeStatusError(
                f"Invalid target status: {target!r}; "
                f"allowed: {sorted(VALID_KNOWLEDGE_STATUSES)}"
            )
        allowed = TRANSITIONS[current]
        if target not in allowed:
            raise KnowledgeStatusError(
                f"Illegal knowledge status transition: "
                f"{current} -> {target}; "
                f"allowed from {current}: {sorted(allowed)}"
            )
        return target

    # --- Предикаты (запрещены строковые проверки вне этого модуля) ---

    @staticmethod
    def is_new(knowledge: Knowledge) -> bool:
        """Знание в статусе NEW."""
        return knowledge.status == KNOWLEDGE_STATUS_NEW

    @staticmethod
    def is_verified(knowledge: Knowledge) -> bool:
        """Знание подтверждено (VERIFIED)."""
        return knowledge.status == KNOWLEDGE_STATUS_VERIFIED

    @staticmethod
    def is_canonical(knowledge: Knowledge) -> bool:
        """Знание каноническое (CANONICAL)."""
        return knowledge.status == KNOWLEDGE_STATUS_CANONICAL

    @staticmethod
    def is_archived(knowledge: Knowledge) -> bool:
        """Знание архивировано (ARCHIVED)."""
        return knowledge.status == KNOWLEDGE_STATUS_ARCHIVED

    @staticmethod
    def is_rejected(knowledge: Knowledge) -> bool:
        """Знание отклонено (REJECTED)."""
        return knowledge.status == KNOWLEDGE_STATUS_REJECTED

    @staticmethod
    def is_conflict(knowledge: Knowledge) -> bool:
        """Знание в статусе CONFLICT."""
        return knowledge.status == KNOWLEDGE_STATUS_CONFLICT

    @staticmethod
    def is_active(knowledge: Knowledge) -> bool:
        """Знание активно (NEW/VERIFIED/CANONICAL — не архив/отклонение)."""
        return knowledge.status in (
            KNOWLEDGE_STATUS_NEW,
            KNOWLEDGE_STATUS_VERIFIED,
            KNOWLEDGE_STATUS_CANONICAL,
            KNOWLEDGE_STATUS_CONFLICT,
        )

"""HKOS Canonicalizer (DS-006 §10, IP-006 §4, DS-006A §4)
======================================================
Определяет, являются ли Knowledge дубликатами (одно и то же знание).

Canonicalizer НЕ имеет права самостоятельно искать похожие знания:
он работает ТОЛЬКО с тем набором Knowledge, который ему передал
Librarian (IP-006 §4). НЕ обращается к Repository.

Current implementation performs structural duplicate detection.

Сравнение детерминированное и структурное (без семантики и similarity):
нормализация (lower + сжатие пробелов) и точное совпадение title.

TODO (DS-007, Retrieval): Semantic canonicalization will be implemented
after Retrieval.
Reason: structural duplicate detection (нормализованный title) не
обнаруживает дубликаты, описанные разными словами; семантика требует
Retrieval/Ranking (DS-007/DS-009).
Remove when: DS-007 Retrieval предоставляет детерминированный механизм
семантического сравнения Knowledge (или явное решение архитектора).
"""

import re

from hkos.repository.models import Knowledge

__all__ = ["Canonicalizer"]

_WS = re.compile(r"\s+")


class Canonicalizer:
    """Поиск дубликатов в переданном наборе Knowledge."""

    @staticmethod
    def normalize(text: str) -> str:
        """Нормализовать текст для сравнения (lower, сжатие пробелов)."""
        return _WS.sub(" ", text.strip().lower())

    @classmethod
    def find_duplicates(
        cls,
        candidate: Knowledge,
        candidates: list[Knowledge],
    ) -> list[Knowledge]:
        """Найти дубликаты candidate среди candidates.

        Args:
            candidate: Проверяемое знание.
            candidates: Набор для сравнения (передаёт Librarian).

        Returns:
            Список Knowledge с идентичным нормализованным title
            (сам candidate исключается).
        """
        target = cls.normalize(candidate.title)
        if not target:
            return []
        return [
            other
            for other in candidates
            if other.id != candidate.id
            and cls.normalize(other.title) == target
        ]

    @classmethod
    def is_duplicate(cls, a: Knowledge, b: Knowledge) -> bool:
        """Являются ли два Knowledge дубликатами (по нормализованному title)."""
        return (
            a.id != b.id
            and cls.normalize(a.title) == cls.normalize(b.title)
            and bool(cls.normalize(a.title))
        )

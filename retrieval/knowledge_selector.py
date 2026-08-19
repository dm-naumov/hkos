"""HKOS Knowledge Selector (DS-008 §13-14, IP-008)
==================================================
Selector ограничивает объём результата — правило Minimal Sufficient
Context: Top N (по умолчанию 20, задаётся конфигурацией).

Запрещено: возвращать весь проект / всю кампанию / все знания.
"""

from hkos.retrieval.ranking_engine import RankedCandidate

__all__ = ["KnowledgeSelector"]


class KnowledgeSelector:
    """Выбор Top N кандидатов (минимально достаточный контекст)."""

    @staticmethod
    def select(
        ranked: list[RankedCandidate],
        top_n: int = 20,
    ) -> list[RankedCandidate]:
        """Выбрать Top N.

        Args:
            ranked: Ранжированные кандидаты (уже отсортированы).
            top_n: Ограничение объёма (конфигурация retrieval.selector.top_n).

        Returns:
            Первые top_n кандидатов.

        """
        if top_n < 0:
            return []
        return ranked[:top_n]

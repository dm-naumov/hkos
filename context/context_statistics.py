"""HKOS Context Statistics (DS-009)
==================================
Агрегированная статистика контекста: состав, исключения, токены,
экономия. Все значения — производные (пересчитываются по документу).
"""

from collections import Counter

from hkos.context.models import ContextDocument

__all__ = ["ContextStatistics"]


class ContextStatistics:
    """Статистика документа контекста (только вычисление)."""

    @staticmethod
    def calculate(context: ContextDocument) -> dict[str, object]:
        """Вычислить статистику контекста.

        Args:
            context: Документ контекста.

        Returns:
            dict: состав, исключения, токены, экономия.

        """
        by_type = Counter(item.entity_type for item in context.items)
        excluded_reasons = Counter(
            item.excluded_reason for item in context.excluded
        )
        included_tokens = context.estimates.estimated_tokens
        excluded_tokens = sum(
            len(str(getattr(i.entity, "title", "") or ""))
            for i in context.excluded
        )
        return {
            "task": context.task,
            "profile": context.profile,
            "snapshot": context.snapshot.snapshot_id if context.snapshot else None,
            "total_items": len(context.items),
            "items_by_type": dict(by_type),
            "excluded_count": len(context.excluded),
            "excluded_by_reason": dict(excluded_reasons),
            "sections_count": len(context.sections),
            "estimated_tokens": included_tokens,
            "excluded_chars": excluded_tokens,
        }

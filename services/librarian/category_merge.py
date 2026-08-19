"""HKOS Category Merge Policy (DS-006A §6)
==========================================
Политика выбора категории при объединении Knowledge.

Логика вынесена из KnowledgeMerger: Merger больше не содержит
логику выбора категории (нет "if category" в Merger).

Текущая политика полностью повторяет существующее поведение DS-006:
    resolve(a_category, b_category) = a_category or b_category

Цель: замена политики в будущих спринтах без изменения Merger.
"""

__all__ = ["CategoryMergePolicy"]


class CategoryMergePolicy:
    """Политика выбора категории объединённого Knowledge."""

    @staticmethod
    def resolve(first_category: str, second_category: str) -> str:
        """Выбрать категорию для объединённого Knowledge.

        Args:
            first_category: Категория первого источника (A).
            second_category: Категория второго источника (B).

        Returns:
            Категория результата: приоритет первой, иначе вторая
            (текущее поведение DS-006).
        """
        return first_category or second_category

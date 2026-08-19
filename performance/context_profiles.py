"""HKOS Context Optimization Profiles (DS-013 ЭТАП 5)
========================================================
Сжатие контекста по профилям NONE/LIGHT/NORMAL/AGGRESSIVE.

НЕЛЬЗЯ удалять (protected-категории):
- версии, решения, ограничения, причины ошибок, технические зависимости.

semantic_equivalence: после компрессии protected-контент сохраняется
(проверяется тестом).
"""

from typing import Final

__all__ = [
    "PROFILE_NONE",
    "PROFILE_LIGHT",
    "PROFILE_NORMAL",
    "PROFILE_AGGRESSIVE",
    "PROTECTED_CATEGORIES",
    "PerformanceContextOptimizer",
    "CompressedContext",
]

PROFILE_NONE: Final[str] = "NONE"
PROFILE_LIGHT: Final[str] = "LIGHT"
PROFILE_NORMAL: Final[str] = "NORMAL"
PROFILE_AGGRESSIVE: Final[str] = "AGGRESSIVE"

# Категории, которые НЕ сжимаются (семантическая неприкосновенность)
PROTECTED_CATEGORIES: Final[frozenset[str]] = frozenset({
    "DECISIONS",
    "FAILURES",
    "CONFIGURATION",
    "OPEN QUESTIONS",
})


class PerformanceContextOptimizer:
    """Сжатие контекста по профилю (только копия; оригинал не меняется)."""

    def __init__(self, profile: str = PROFILE_NORMAL) -> None:
        """Инициализация.

        Args:
            profile: PROFILE_NONE/LIGHT/NORMAL/AGGRESSIVE.
        """
        self._profile = profile

    @property
    def profile(self) -> str:
        return self._profile

    def compress(self, context: object) -> object:
        """Сжать контекст (возвращает НОВЫЙ объект; оригинал не изменён).

        Профили:
        - NONE: полный контекст (без изменений);
        - LIGHT: удаление дублей по заголовкам;
        - NORMAL: сжатие второстепенных деталей (лимит записей на секцию,
          protected-секции не трогаются);
        - AGGRESSIVE: минимальный достаточный контекст (protected + топ).
        """
        if self._profile == PROFILE_NONE:
            return context
        sections = self._sections(context)
        if sections is None:
            return context
        if self._profile == PROFILE_LIGHT:
            return self._dedup(sections)
        limit = 0 if self._profile == PROFILE_AGGRESSIVE else 3
        return self._trim(sections, limit)

    # ---- внутренние ----

    def _sections(self, context: object) -> dict[str, list[object]] | None:
        """Секции контекста (items по категориям) или None."""
        sections = getattr(context, "sections", None)
        if isinstance(sections, dict) and sections:
            return {k: list(v) if isinstance(v, list) else [] for k, v in sections.items()}
        items = getattr(context, "items", None)
        if isinstance(items, list):
            grouped: dict[str, list[object]] = {}
            for item in items:
                category = self._item_category(item)
                grouped.setdefault(category, []).append(item)
            return grouped
        return None

    @staticmethod
    def _item_category(item: object) -> str:
        """Категория элемента контекста (для protected-проверки).

        ContextItem -> категория по сущности (entity.category/kind/
        entity_type); иначе — атрибут category самого элемента.
        """
        entity = getattr(item, "entity", None)
        if entity is not None:
            category = str(getattr(entity, "category", "") or "")
            kind = str(getattr(entity, "kind", "") or "")
            entity_type = str(getattr(item, "entity_type", "") or "")
            if category == "DECISION" or entity_type == "decision":
                return "DECISIONS"
            if category == "FAILURE" or kind == "negative":
                return "FAILURES"
            if category == "CONFIGURATION":
                return "CONFIGURATION"
            if entity_type == "artifact":
                return "ARTIFACTS"
            return "CANONICAL KNOWLEDGE"
        return str(getattr(item, "category", "") or "OTHER")

    def _dedup(self, sections: dict[str, list[object]]) -> object:
        """LIGHT: удаление дублей по заголовкам внутри секции."""
        result: dict[str, list[object]] = {}
        for category, entries in sections.items():
            seen: set[str] = set()
            unique: list[object] = []
            for entry in entries:
                title = str(getattr(entry, "title", "") or getattr(entry, "id", ""))
                if title in seen:
                    continue
                seen.add(title)
                unique.append(entry)
            result[category] = unique
        return CompressedContext(result)

    def _trim(self, sections: dict[str, list[object]], limit: int) -> object:
        """NORMAL/AGGRESSIVE: лимит записей; protected-секции сохраняются."""
        result: dict[str, list[object]] = {}
        for category, entries in sections.items():
            if category in PROTECTED_CATEGORIES:
                result[category] = entries      # protected сохраняется
            elif limit == 0:
                result[category] = []           # AGGRESSIVE: удалить
            else:
                result[category] = entries[:limit]
        return CompressedContext(result)


class CompressedContext:
    """Результат сжатия (новый контекст; оригинал не изменён)."""

    def __init__(self, sections: dict[str, list[object]]) -> None:
        self.sections = sections

    def item_count(self) -> int:
        return sum(len(v) for v in self.sections.values())

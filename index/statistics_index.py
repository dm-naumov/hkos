"""HKOS Statistics Index (DS-007 §7)
=================================
Агрегированные счётчики проекта: knowledge, decisions, campaigns,
projects, artifacts.

Счётчики — производные данные: пересчитываются при build/rebuild/
optimize (из Entity Index) и обновляются дельтой при incremental
update/remove. Корректность проверяется Index Validator.
"""

from typing import Any

from hkos.index.entity_index import EntityIndex

__all__ = ["StatisticsIndex"]

# Маппинг типов сущностей (repo _type_name) -> ключ статистики.
_STAT_KEYS: dict[str, str] = {
    "knowledge": "knowledge",
    "decision": "decisions",
    "campaign": "campaigns",
    "project": "projects",
    "artifact": "artifacts",
}

_STAT_TYPES: tuple[str, ...] = (
    "knowledge", "decisions", "campaigns", "projects", "artifacts",
)


class StatisticsIndex:
    """Агрегированная статистика проекта."""

    def __init__(self, data: dict[str, Any] | None = None) -> None:
        """Инициализация из данных (None — нулевые счётчики)."""
        loaded = data or {}
        statistics = loaded.get("statistics", {})
        self._data: dict[str, Any] = {
            "statistics": {
                key: int(statistics.get(key, 0) or 0) for key in _STAT_TYPES
            }
        }

    def get(self) -> dict[str, int]:
        """Текущие счётчики (копия)."""
        return dict(self._data["statistics"])

    def increment(self, entity_type: str, delta: int) -> None:
        """Изменить счётчик типа на delta (инкрементальное обновление)."""
        key = _STAT_KEYS.get(entity_type)
        if key is None:
            return
        self._data["statistics"][key] = max(
            0, self._data["statistics"][key] + delta
        )

    def recompute(self, entity_index: EntityIndex) -> None:
        """Пересчитать счётчики из Entity Index (build/rebuild/optimize)."""
        counts = entity_index.count_by_type()
        for entity_type, key in _STAT_KEYS.items():
            self._data["statistics"][key] = counts.get(entity_type, 0)

    def data(self) -> dict[str, Any]:
        """Данные для персистентности."""
        return self._data

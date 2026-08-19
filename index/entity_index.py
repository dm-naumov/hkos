"""HKOS Entity Index (DS-007 §7)
==============================
Индекс сущностей: реестр всех проиндексированных объектов
(Project, Campaign, Knowledge, Decision, Artifact).

Используется для проверки целостности, статистики и исключения
битых ссылок. Хранение (JSON):
    {"entities": {id: {"id", "project", "type", "title", "status",
                        "category", "tags", "updated_at"}}}
"""

from typing import Any

__all__ = ["EntityIndex"]


class EntityIndex:
    """Реестр проиндексированных сущностей."""

    def __init__(self, data: dict[str, Any] | None = None) -> None:
        """Инициализация из данных (None — пустой индекс)."""
        self._data: dict[str, Any] = data or {"entities": {}}

    def upsert(
        self,
        entity: Any,
        entity_type: str,
        project: str,
    ) -> None:
        """Добавить или обновить запись сущности."""
        tags = [str(t) for t in (getattr(entity, "tags", None) or [])]
        title = (
            getattr(entity, "title", None)
            or getattr(entity, "name", None)
            or getattr(entity, "goal", None)
            or ""
        )
        self._data["entities"][entity.id] = {
            "id": entity.id,
            "project": project,
            "type": entity_type,
            "title": str(title),
            "status": str(getattr(entity, "status", "") or ""),
            "category": str(getattr(entity, "category", "") or ""),
            "tags": tags,
            "updated_at": str(getattr(entity, "updated_at", "") or ""),
        }

    def remove(self, entity_id: str) -> None:
        """Удалить запись сущности."""
        self._data["entities"].pop(entity_id, None)

    def get(self, entity_id: str) -> dict[str, Any] | None:
        """Запись сущности (query-контракт)."""
        record = self._data["entities"].get(entity_id)
        if not isinstance(record, dict):
            return None
        return record

    def ids(self) -> list[str]:
        """Все id проиндексированных сущностей."""
        return list(self._data["entities"].keys())

    def count(self) -> int:
        """Количество сущностей."""
        return len(self._data["entities"])

    def count_by_type(self) -> dict[str, int]:
        """Количество сущностей по типам."""
        counts: dict[str, int] = {}
        for record in self._data["entities"].values():
            entity_type = record["type"]
            counts[entity_type] = counts.get(entity_type, 0) + 1
        return counts

    def data(self) -> dict[str, Any]:
        """Данные для персистентности."""
        return self._data

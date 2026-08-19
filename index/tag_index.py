"""HKOS Tag Index (DS-007 §7)
==========================
Индекс тегов: тег -> список сущностей (знания, проекты, кампании...).

Позволяет быстро получать все объекты с тегом (query-контракт для
Retriever). Хранение (JSON):
    {"tags": {tag: [{"id", "type", "project"}]},
     "entity_tags": {entity_id: [tags]}}
"""

from typing import Any

__all__ = ["TagIndex"]


def indexable_tags(entity: Any) -> list[str]:
    """Теги сущности (у сущностей без тегов — пустой список)."""
    tags = getattr(entity, "tags", None)
    if not tags:
        return []
    return [str(tag) for tag in tags]


class TagIndex:
    """Индекс тегов (тег -> сущности)."""

    def __init__(self, data: dict[str, Any] | None = None) -> None:
        """Инициализация из данных (None — пустой индекс).

        DS-015 ЭТАП 4: _tag_ids — in-memory set-индекс для O(1) dedup
        при add (устраняет O(N^2) на общих тегах; формат и поведение
        НЕ изменены).
        """
        self._data: dict[str, Any] = data or {
            "tags": {},
            "entity_tags": {},
        }
        self._tag_ids: dict[str, set[str]] = {}
        for tag, entries in self._data.get("tags", {}).items():
            self._tag_ids[tag] = {e["id"] for e in entries}

    def add(
        self,
        entity_id: str,
        entity_type: str,
        project: str,
        tags: list[str],
    ) -> None:
        """Проиндексировать теги сущности."""
        tags_index: dict[str, list[dict[str, str]]] = self._data["tags"]
        for tag in tags:
            ids = self._tag_ids.setdefault(tag, set())
            if entity_id not in ids:
                ids.add(entity_id)
                entries = tags_index.setdefault(tag, [])
                entries.append({
                    "id": entity_id,
                    "type": entity_type,
                    "project": project,
                })
        self._data["entity_tags"][entity_id] = tags

    def remove(self, entity_id: str) -> None:
        """Удалить сущность из индекса тегов."""
        tags: list[str] = self._data["entity_tags"].pop(entity_id, [])
        tags_index: dict[str, list[dict[str, str]]] = self._data["tags"]
        for tag in tags:
            entries = tags_index.get(tag)
            if not entries:
                continue
            remaining = [e for e in entries if e["id"] != entity_id]
            if remaining:
                tags_index[tag] = remaining
            else:
                del tags_index[tag]
            ids = self._tag_ids.get(tag)
            if ids is not None:
                ids.discard(entity_id)

    def get_by_tag(self, tag: str) -> list[dict[str, str]]:
        """Query-контракт: все сущности с тегом (по индексу)."""
        return list(self._data["tags"].get(tag, []))

    def entity_tags(self, entity_id: str) -> list[str]:
        """Теги сущности."""
        return list(self._data["entity_tags"].get(entity_id, []))

    def tag_count(self) -> int:
        """Количество уникальных тегов."""
        return len(self._data["tags"])

    def data(self) -> dict[str, Any]:
        """Данные для персистентности."""
        return self._data

"""HKOS Keyword Index (DS-007 §7)
==============================
Полнотекстовый индекс слов: слово -> список сущностей.

Только инфраструктура (построение/обновление/поиск по индексу).
Сам поиск (Retrieval) — предмет DS-008; здесь query-методы
являются контрактом для Retriever.

Хранение (JSON, будущая миграция в SQLite без изменения API):
    {"postings": {word: [{"id", "type", "project"}]},
     "entity_words": {entity_id: [words]}}
"""

import re
from typing import Any

__all__ = ["KeywordIndex"]

_WORD_SPLIT = re.compile(r"[^0-9a-zA-Zа-яА-ЯёЁ]+")
_MIN_WORD_LEN: int = 2


def indexable_text(entity: Any) -> str:
    """Смысловое содержимое сущности для индексации слов.

    Индексируются: title/name, body/description/goal, category, kind.
    """
    parts: list[str] = []
    for attr in ("title", "name", "body", "description", "goal",
                 "category", "kind", "decision", "reason"):
        value = getattr(entity, attr, None)
        if value:
            parts.append(str(value))
    return " ".join(parts)


class KeywordIndex:
    """Инвертированный индекс слов (posting list)."""

    def __init__(self, data: dict[str, Any] | None = None) -> None:
        """Инициализация из данных (None — пустой индекс)."""
        self._data: dict[str, Any] = data or {
            "postings": {},
            "entity_words": {},
        }
        # DS-015 ЭТАП 4: set-индекс для O(1) dedup при add (устраняет
        # O(N^2) на общих словах; формат данных не изменён)
        self._word_ids: dict[str, set[str]] = {}
        for word, entries in self._data.get("postings", {}).items():
            self._word_ids[word] = {e["id"] for e in entries}

    @staticmethod
    def tokenize(text: str) -> list[str]:
        """Детерминированная токенизация: lower, split, len>=2, dedup."""
        words = {
            token.lower()
            for token in _WORD_SPLIT.split(text)
            if len(token) >= _MIN_WORD_LEN
        }
        return sorted(words)

    def add(
        self,
        entity_id: str,
        entity_type: str,
        project: str,
        text: str,
    ) -> None:
        """Проиндексировать слова сущности."""
        words = self.tokenize(text)
        postings: dict[str, list[dict[str, str]]] = self._data["postings"]
        for word in words:
            ids = self._word_ids.setdefault(word, set())
            if entity_id not in ids:
                ids.add(entity_id)
                postings.setdefault(word, []).append({
                    "id": entity_id,
                    "type": entity_type,
                    "project": project,
                })
        self._data["entity_words"][entity_id] = words

    def remove(self, entity_id: str) -> None:
        """Удалить сущность из индекса (по её словам)."""
        words: list[str] = self._data["entity_words"].pop(entity_id, [])
        postings: dict[str, list[dict[str, str]]] = self._data["postings"]
        for word in words:
            entries = postings.get(word)
            if not entries:
                continue
            remaining = [e for e in entries if e["id"] != entity_id]
            if remaining:
                postings[word] = remaining
            else:
                del postings[word]
            ids = self._word_ids.get(word)
            if ids is not None:
                ids.discard(entity_id)

    def search(self, word: str) -> list[dict[str, str]]:
        """Query-контракт для Retriever: сущности по слову (по индексу)."""
        return list(self._data["postings"].get(word.lower(), []))

    def entity_words(self, entity_id: str) -> list[str]:
        """Слова, проиндексированные для сущности."""
        return list(self._data["entity_words"].get(entity_id, []))

    def word_count(self) -> int:
        """Количество уникальных слов в индексе."""
        return len(self._data["postings"])

    def data(self) -> dict[str, Any]:
        """Данные для персистентности."""
        return self._data

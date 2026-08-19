"""HKOS Query Parser (DS-008 §8, IP-008)
====================================
QueryParser анализирует ТЕКСТ запроса и определяет:

- Project (подсказку);
- Campaign (подсказку);
- Topic;
- Keywords;
- Entities;
- Task Type (intent);
- Constraints (например, include_history).

Parser НЕ имеет права обращаться ни к Repository, ни к Index —
он только анализирует текст. Словари проектов/тем/сущностей берутся
из конфигурации (retrieval.parser.*).

Детерминированный: одинаковый запрос -> одинаковый результат.
"""

import re
from dataclasses import dataclass, field

from hkos.core.config import ConfigLoader

__all__ = ["ParsedQuery", "QueryParser"]

_WORD_SPLIT = re.compile(r"[^0-9a-zA-Zа-яА-ЯёЁ_\-]+")


@dataclass
class ParsedQuery:
    """Результат разбора запроса (только текстовая информация)."""

    query: str = ""
    project_hint: str = ""
    campaign_hint: str = ""
    topic: str = ""
    keywords: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    task_type: str = ""
    include_history: bool = False

    def as_dict(self) -> dict[str, object]:
        """Результат разбора как словарь."""
        return {
            "query": self.query,
            "project_hint": self.project_hint,
            "campaign_hint": self.campaign_hint,
            "topic": self.topic,
            "keywords": self.keywords,
            "entities": self.entities,
            "task_type": self.task_type,
            "include_history": self.include_history,
        }


class QueryParser:
    """Детерминированный анализатор текстового запроса (без I/O)."""

    _HISTORY_MARKERS: tuple[str, ...] = (
        "истори", "archive", "архив", "старые версии", "history",
    )
    _CAMPAIGN_MARKERS: tuple[str, ...] = (
        "кампани", "campaign",
    )

    def __init__(self, config: ConfigLoader | None = None) -> None:
        """Инициализация парсера.

        Args:
            config: ConfigLoader; словари retrieval.parser.*
                (пустые, если конфигурация недоступна).

        """
        self._config = config

    # --- Словари из конфигурации ---

    def _projects(self) -> dict[str, str]:
        """Словарь имён проектов (name -> каноническое имя)."""
        if self._config is None:
            return {}
        raw = self._config.get("retrieval.parser.projects", {})
        if isinstance(raw, dict):
            return {str(k).lower(): str(v) for k, v in raw.items()}
        return {}

    def _topics(self) -> list[str]:
        """Список известных тем."""
        if self._config is None:
            return []
        raw = self._config.get("retrieval.parser.topics", [])
        if isinstance(raw, list):
            return [str(t).lower() for t in raw]
        return []

    def _entities(self) -> list[str]:
        """Список инженерных сущностей."""
        if self._config is None:
            return []
        raw = self._config.get("retrieval.parser.entities", [])
        if isinstance(raw, list):
            return [str(e).lower() for e in raw]
        return []

    def _intents(self) -> dict[str, list[str]]:
        """Словарь типов задач (intent -> маркеры)."""
        if self._config is None:
            return {}
        raw = self._config.get("retrieval.parser.intents", {})
        if isinstance(raw, dict):
            return {
                str(k): [str(m).lower() for m in v]
                for k, v in raw.items()
                if isinstance(v, list)
            }
        return {}

    def _stopwords(self) -> set[str]:
        """Стоп-слова."""
        if self._config is None:
            return set()
        raw = self._config.get("retrieval.parser.stopwords", [])
        if isinstance(raw, list):
            return {str(w).lower() for w in raw}
        return set()

    # --- Разбор ---

    def _tokenize(self, text: str) -> list[str]:
        """Токенизация: lower, split, без стоп-слов, len>=2."""
        stopwords = self._stopwords()
        tokens = [
            token.lower().strip("_-")
            for token in _WORD_SPLIT.split(text)
            if len(token.strip("_-")) >= 2
            and token.lower().strip("_-") not in stopwords
        ]
        return tokens

    def parse(self, query: str) -> ParsedQuery:
        """Разобрать текстовый запрос.

        Args:
            query: Текст запроса.

        Returns:
            ParsedQuery (только текстовая информация; без I/O).

        """
        lowered = query.lower()
        parsed = ParsedQuery(query=query)
        tokens = self._tokenize(query)

        # Constraints
        parsed.include_history = any(
            marker in lowered for marker in self._HISTORY_MARKERS
        )

        # Project hint (самое длинное совпадение имени из словаря)
        projects = self._projects()
        best_project = ""
        best_len = 0
        for alias, canonical in projects.items():
            if alias in lowered and len(alias) > best_len:
                best_project = canonical
                best_len = len(alias)
        parsed.project_hint = best_project

        # Campaign hint: маркер "кампани/campaign" + следующее слово
        campaign_match = re.search(
            r"(?:кампани|campaign)\w*\s*:?\s*([a-zа-я0-9_\-]+)",
            lowered,
        )
        if campaign_match:
            parsed.campaign_hint = campaign_match.group(1)

        # Topic: первый известный topic в тексте
        topics = self._topics()
        for topic in topics:
            if topic in lowered:
                parsed.topic = topic
                break

        # Entities: известные инженерные сущности в тексте (в порядке появления)
        entities = self._entities()
        seen: set[str] = set()
        for token in tokens:
            if token in entities and token not in seen:
                seen.add(token)
                parsed.entities.append(token)

        # Keywords: все токены, кроме распознанных сущностей
        parsed.keywords = [t for t in tokens if t not in seen]

        # Task type (intent): первый совпавший маркер
        intents = self._intents()
        for intent, markers in intents.items():
            if any(marker in lowered for marker in markers):
                parsed.task_type = intent
                break

        return parsed

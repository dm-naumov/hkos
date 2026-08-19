"""HKOS Candidate Builder (DS-008 §9, IP-008)
==========================================
CandidateBuilder собирает кандидатов ИСКЛЮЧИТЕЛЬНО через Query Contract.

Порядок (IP-008):
    Keyword -> Tags -> Entities -> Relations -> Merge

- Q1 keyword_search по каждому ключевому слову;
- Q2 tag_search по темам/сущностям как тегам;
- Q3 entity_get для явных UUID сущностей в запросе;
- Q4 relations_of_knowledge для явных UUID знаний (расширение на 1 хоп);
- Merge: дедупликация, фильтр по проекту, ограничение max_candidates.

Никаких обращений к Repository/Storage — только Query Contract.
"""

from dataclasses import dataclass, field
from typing import Any

from hkos.index.query_contract import IndexEntry
from hkos.retrieval.query_parser import ParsedQuery

__all__ = ["CandidateBuilder"]


@dataclass
class CandidateSet:
    """Результат построения кандидатов."""

    entries: list[IndexEntry] = field(default_factory=list)
    sources: dict[str, list[str]] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        """Результат как словарь."""
        return {
            "count": len(self.entries),
            "entries": [
                {"id": e.id, "type": e.type, "project": e.project}
                for e in self.entries
            ],
        }


class CandidateBuilder:
    """Сбор кандидатов через Query Contract (Q1–Q4)."""

    def __init__(
        self,
        max_candidates: int = 200,
        keyword_limit: int = 50,
    ) -> None:
        """Инициализация строителя кандидатов.

        Args:
            max_candidates: Ограничение размера набора кандидатов.
            keyword_limit: Ограничение числа ключевых слов для Q1.

        """
        self._max_candidates = max_candidates
        self._keyword_limit = keyword_limit

    def _add(
        self,
        candidate: CandidateSet,
        entries: list[IndexEntry],
        source: str,
        project: str | None,
    ) -> None:
        """Добавить записи с дедупликацией и фильтром по проекту."""
        for entry in entries:
            if project is not None and entry.project != project:
                continue
            if entry.id not in candidate.sources:
                candidate.sources[entry.id] = [source]
                candidate.entries.append(entry)
            else:
                if source not in candidate.sources[entry.id]:
                    candidate.sources[entry.id].append(source)

    def build(
        self,
        parsed: ParsedQuery,
        project: str | None = None,
        snapshot: Any | None = None,
    ) -> CandidateSet:
        """Собрать кандидатов через Query Contract (снимок индекса).

        Args:
            parsed: Разобранный запрос.
            project: UUID проекта (фильтр; None — без фильтра).
            snapshot: IndexSnapshot (снимок индексов на запрос).

        Returns:
            CandidateSet (дедуплицированные записи, ограниченные по объёму).

        """
        if snapshot is None:
            return CandidateSet()
        candidate = CandidateSet()

        # Q1 Keyword
        for keyword in parsed.keywords[: self._keyword_limit]:
            self._add(
                candidate,
                snapshot.keyword_search(keyword),
                f"keyword:{keyword}",
                project,
            )

        # Q2 Tag (темы и сущности как теги)
        tag_terms = [parsed.topic] if parsed.topic else []
        tag_terms.extend(parsed.entities)
        for tag in tag_terms:
            self._add(
                candidate,
                snapshot.tag_search(tag),
                f"tag:{tag}",
                project,
            )

        # Q3 Entity (явные UUID в запросе)
        for token in parsed.keywords:
            record = snapshot.entity_get(token)
            if record is not None:
                self._add(
                    candidate,
                    [IndexEntry(id=record.id, type=record.type, project=record.project)],
                    "entity",
                    project,
                )

        # Q4 Relations (явные UUID знаний: расширение на 1 хоп)
        for token in parsed.keywords:
            relations = snapshot.relations_of_knowledge(token)
            related: list[IndexEntry] = []
            for relation in relations:
                for node in (relation.source_id, relation.target_id):
                    if node != token:
                        record = snapshot.entity_get(node)
                        if record is not None:
                            related.append(
                                IndexEntry(
                                    id=record.id,
                                    type=record.type,
                                    project=record.project,
                                )
                            )
            self._add(candidate, related, "relation", project)

        # Ограничение объёма (производительность, bounded work)
        candidate.entries = candidate.entries[: self._max_candidates]
        return candidate

"""HKOS Retriever (DS-008 §7, IP-008 Query Pipeline)
=================================================
Оркестрация конвейера Retrieval (ровно эти стадии, IP-008):

    Query
    -> Query Parser
    -> Candidate Builder
    -> Ranking Engine
    -> Knowledge Filter
    -> Relationship Traverser
    -> Knowledge Selector
    -> Retrieval Result

Никаких дополнительных стадий.
"""

from typing import Any

from hkos.retrieval.candidate_builder import CandidateBuilder
from hkos.retrieval.knowledge_filter import KnowledgeFilter
from hkos.retrieval.knowledge_selector import KnowledgeSelector
from hkos.retrieval.query_parser import ParsedQuery, QueryParser
from hkos.retrieval.ranking_engine import RankedCandidate, RankingEngine
from hkos.retrieval.relationship_traverser import RelationshipTraverser

__all__ = ["Retriever"]


class Retriever:
    """Конвейер Retrieval (Parser -> Builder -> Ranking -> Filter ->
    Traverser -> Selector).
    """

    def __init__(
        self,
        parser: QueryParser,
        builder: CandidateBuilder,
        ranking: RankingEngine,
        filter_: KnowledgeFilter,
        traverser: RelationshipTraverser,
        selector: KnowledgeSelector,
    ) -> None:
        """Инициализация конвейера (стадии инжектируются)."""
        self._parser = parser
        self._builder = builder
        self._ranking = ranking
        self._filter = filter_
        self._traverser = traverser
        self._selector = selector

    def run(
        self,
        query: str,
        project: str | None = None,
        campaign_id: str | None = None,
        top_n: int | None = None,
        include_history: bool = False,
        snapshot: Any | None = None,
    ) -> list[RankedCandidate]:
        """Запустить конвейер и вернуть выбранные кандидаты.

        Args:
            query: Текст запроса.
            project: UUID проекта.
            campaign_id: UUID кампании.
            top_n: Ограничение результата (None -> конфигурация).
            include_history: Включить исторические статусы.
            snapshot: IndexSnapshot (снимок индексов на запрос).

        Returns:
            Выбранные RankedCandidate (Top N).

        """
        # 1. Query Parser
        parsed = self._parser.parse(query)
        return self.run_parsed(
            parsed,
            project=project,
            campaign_id=campaign_id,
            top_n=top_n,
            include_history=include_history,
            snapshot=snapshot,
        )

    def run_parsed(
        self,
        parsed: ParsedQuery,
        project: str | None = None,
        campaign_id: str | None = None,
        top_n: int | None = None,
        include_history: bool = False,
        snapshot: Any | None = None,
        refine_limit: int = 60,
    ) -> list[RankedCandidate]:
        """Конвейер по уже разобранному запросу."""
        # 2. Candidate Builder (только Query Contract, снимок индекса)
        candidates = self._builder.build(parsed, project, snapshot)

        # 3. Ranking Engine (двухфазный: index-only + Top-K)
        ranked = self._ranking.rank(
            candidates, parsed, project, campaign_id,
            snapshot=snapshot, refine_limit=refine_limit,
        )

        # 4. Knowledge Filter
        filtered = self._filter.filter(
            ranked, include_history or parsed.include_history
        )

        # 5. Relationship Traverser (Q4, снимок индекса)
        expanded = self._traverser.traverse(filtered, project or "", snapshot)

        # 6. Knowledge Selector (Top N)
        selected = self._selector.select(expanded, top_n or 0)
        return selected

    def run_search(
        self,
        query: str,
        project: str | None = None,
        campaign_id: str | None = None,
        top_n: int | None = None,
        include_history: bool = False,
        snapshot: Any | None = None,
        refine_limit: int = 60,
    ) -> list[RankedCandidate]:
        """Прямой конвейер без обхода связей (search).

        Стадии: Parser -> Builder -> Ranking -> Filter -> Selector.
        """
        parsed = self._parser.parse(query)
        built = self._builder.build(parsed, project, snapshot)
        ranked = self._ranking.rank(
            built, parsed, project, campaign_id,
            snapshot=snapshot, refine_limit=refine_limit,
        )
        filtered = self._filter.filter(
            ranked, include_history or parsed.include_history
        )
        return self._selector.select(filtered, top_n or 0)

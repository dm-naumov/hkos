"""HKOS Retrieval Layer (DS-008)
===============================
Retrieval Engine — поиск минимального набора релевантных знаний.

Использует ИСКЛЮЧИТЕЛЬНО:
- RepositoryManager (сущности по UUID);
- Query Contract Q1-Q5 (HKOS-INDEX-CONTRACT-001, FROZEN).

Никаких обращений к Storage/IndexStore/Filesystem/Repository.list().
"""

from hkos.retrieval.candidate_builder import CandidateBuilder, CandidateSet
from hkos.retrieval.exceptions import RetrievalError, RetrievalScopeError
from hkos.retrieval.knowledge_filter import KnowledgeFilter
from hkos.retrieval.knowledge_selector import KnowledgeSelector
from hkos.retrieval.query_parser import ParsedQuery, QueryParser
from hkos.retrieval.ranking_engine import RankedCandidate, RankingEngine
from hkos.retrieval.relationship_traverser import RelationshipTraverser
from hkos.retrieval.retrieval_engine import (
    RetrievalEngine,
    RetrievalExplanation,
    RetrievalItem,
    RetrievalResult,
)
from hkos.retrieval.retriever import Retriever

__all__ = [
    "RetrievalEngine",
    "Retriever",
    "QueryParser",
    "ParsedQuery",
    "CandidateBuilder",
    "CandidateSet",
    "RankingEngine",
    "RankedCandidate",
    "KnowledgeFilter",
    "KnowledgeSelector",
    "RelationshipTraverser",
    "RetrievalResult",
    "RetrievalItem",
    "RetrievalExplanation",
    "RetrievalError",
    "RetrievalScopeError",
]

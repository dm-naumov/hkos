"""Knowledge Integrity Contract — executable target contract tests.

INTENT: these tests express the TARGET Knowledge Integrity Contract as
defined in docs/design/adr-001-knowledge-integrity-contract.md. They are
not yet satisfied by v1.2.0; each confirmed deviation is marked with a
strict XFAIL carrying its KI-ID. When a future lifecycle/retrieval PR fixes
a deviation, remove the marker: the test then runs as an ordinary
regression test. No XFAIL may be removed without the corresponding
implementation landing.

Rules honored here:
- strict=True everywhere; reason contains the KI-ID;
- no module-level xfail, no skip, no dummy asserts;
- each test exercises real observable behavior through public components
  (Librarian, KnowledgeFilter, retrieval pipeline, MCP save handler).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.index import IndexCache, IndexEngine, IndexQueryExecutor, IndexStore
from hkos.mcp_server.context import build_context
from hkos.mcp_server.tools import tool_save
from hkos.repository.knowledge_relations import KnowledgeRelation, RelationType
from hkos.repository.models import (
    KNOWLEDGE_STATUS_ARCHIVED,
    KNOWLEDGE_STATUS_NEW as MODELS_STATUS_NEW,
    VALID_KNOWLEDGE_STATUSES as MODELS_VALID_STATUSES,
    Knowledge,
)
from hkos.repository.repository_manager import RepositoryManager
from hkos.retrieval import RetrievalEngine
from hkos.retrieval.knowledge_filter import KnowledgeFilter
from hkos.retrieval.ranking_engine import RankedCandidate
from hkos.services.librarian import Librarian
from hkos.services.librarian.exceptions import KnowledgeStatusError
from hkos.services.librarian.knowledge_status import (
    KNOWLEDGE_STATUS_CANONICAL,
    VALID_KNOWLEDGE_STATUSES as SERVICES_VALID_STATUSES,
)
from hkos.services.project_manager import ProjectManager
from hkos.storage import StorageEngine

_ALL_STATUSES = [
    "NEW", "VERIFIED", "CANONICAL", "SUPERSEDED",
    "CONFLICT", "REJECTED", "ARCHIVED",
]


class ContractFixture:
    """Repository + Index + Librarian + Retrieval over a tmp data root."""

    def __init__(self, tmp_path: Path) -> None:
        cfg = ConfigLoader(profile="development")
        cfg.load()
        self.engine = StorageEngine(
            root=str(tmp_path), config=cfg, logger=HKOSLogger(),
            version=VersionManager())
        self.engine.initialize()
        self.repos = RepositoryManager(self.engine)
        self.projects = ProjectManager(self.repos, HKOSLogger())
        self.librarian = Librarian(self.repos, HKOSLogger())
        store = IndexStore(self.engine)
        cache = IndexCache()
        self.index = IndexEngine(self.repos, store, HKOSLogger(), cache=cache)
        qc = IndexQueryExecutor(store, cache=cache)
        self.retrieval = RetrievalEngine(self.repos, qc, cfg, HKOSLogger())

    def project(self) -> str:
        return self.projects.create(name="P", tags=["t"]).id

    def register(
        self, pid: str, title: str, body: str = "body text",
        tags: list[str] | None = None,
        relations: list[KnowledgeRelation] | None = None,
    ) -> Knowledge:
        knowledge = self.librarian.register(
            pid, Knowledge(
                title=title, body=body, tags=tags or [],
                relations=relations or []))
        self.index.update(pid, knowledge.id, "knowledge")
        return knowledge

    def canonicalize(self, pid: str, knowledge_id: str) -> Knowledge:
        saved = self.librarian.canonicalize(pid, knowledge_id)
        self.index.update(pid, knowledge_id, "knowledge")
        return saved

    def archive(self, pid: str, knowledge_id: str) -> Knowledge:
        saved = self.librarian.archive(pid, knowledge_id)
        self.index.update(pid, knowledge_id, "knowledge")
        return saved

    @staticmethod
    def _candidate(status: str, title: str = "k") -> RankedCandidate:
        return RankedCandidate(
            entity=Knowledge(title=title, status=status),
            entity_type="knowledge", score=1.0, factors={}, sources=[],
        )


class TestDefaultEligibility:
    """Target: ordinary retrieval eligibility admits CANONICAL only."""

    def test_filter_admits_only_canonical(self, tmp_path: Path) -> None:
        """KI-001: default eligibility keeps only CANONICAL.

        The policy is expressed as a positive allowlist, not a denylist.
        """
        fx = ContractFixture(tmp_path)
        kept = KnowledgeFilter.filter([
            fx._candidate(status, title=f"k-{status}")
            for status in _ALL_STATUSES
        ])
        assert [k.entity.status for k in kept] == [KNOWLEDGE_STATUS_CANONICAL]

    def test_verified_not_admitted(self, tmp_path: Path) -> None:
        """KI-001: VERIFIED is not admitted by default eligibility."""
        fx = ContractFixture(tmp_path)
        kept = KnowledgeFilter.filter([fx._candidate("VERIFIED")])
        assert kept == []

    def test_conflict_not_admitted(self, tmp_path: Path) -> None:
        """KI-001: CONFLICT is not admitted by default eligibility."""
        fx = ContractFixture(tmp_path)
        kept = KnowledgeFilter.filter([fx._candidate("CONFLICT")])
        assert kept == []

    def test_new_not_in_ordinary_retrieval(self, tmp_path: Path) -> None:
        """KI-001: a NEW knowledge is not returned by ordinary retrieval."""
        fx = ContractFixture(tmp_path)
        pid = fx.project()
        fx.register(pid, "zxqnew observation fact", body="zxqnew body")
        result = fx.retrieval.retrieve("zxqnew", project_id=pid, top_n=10)
        titles = [item.entity.title for item in result.items]
        assert "zxqnew observation fact" not in titles


class TestGraphEligibility:
    """Target: graph traversal cannot bypass eligibility."""

    def test_archived_relation_target_not_retrieved(
        self, tmp_path: Path
    ) -> None:
        """KI-002: ARCHIVED target of a relation is not returned.

        The anchor is CANONICAL and points at an ARCHIVED neighbor; the
        neighbor must not surface in ordinary retrieval after graph
        expansion.
        """
        fx = ContractFixture(tmp_path)
        pid = fx.project()
        b = fx.register(pid, "ki002 archived target", body="bb body")
        fx.archive(pid, b.id)
        a = fx.register(
            pid,
            "ki002 alpha anchor",
            body="alpha specific body",
            tags=["alpha"],
            relations=[KnowledgeRelation(
                relation_type=RelationType.REFERENCE_TO,
                source_id="", target_id=b.id)])
        fx.librarian.verify(pid, a.id)
        fx.canonicalize(pid, a.id)

        result = fx.retrieval.retrieve("alpha", project_id=pid, top_n=10)
        titles = [item.entity.title for item in result.items]
        assert "ki002 archived target" not in titles


class TestObservationAndCanonicalization:
    """Target: observation is not canonical; verify is separate."""

    def test_save_without_elevated_action_not_canonical(
        self, tmp_path: Path
    ) -> None:
        """KI-003: a plain save (no elevated action) creates no CANONICAL.

        Executed through the real MCP save handler on a built context.
        """
        ctx = build_context(str(tmp_path / "root"), "production")
        result = tool_save(ctx, {
            "project": "KI003",
            "title": "ki003 plain save",
            "body": "body",
        })
        assert result["status"] != KNOWLEDGE_STATUS_CANONICAL

    def test_new_cannot_be_canonicalized_without_verify(
        self, tmp_path: Path
    ) -> None:
        """KI-004: canonicalize on NEW requires a separate verify first."""
        fx = ContractFixture(tmp_path)
        pid = fx.project()
        k = fx.register(pid, "ki004 claim")
        with pytest.raises(KnowledgeStatusError):
            fx.canonicalize(pid, k.id)


class TestStatusVocabulary:
    """Target: one authoritative status vocabulary."""

    def test_single_status_vocabulary(self, tmp_path: Path) -> None:
        """KI-005: repository and Librarian share one vocabulary object."""
        from hkos.services.librarian.knowledge_status import (
            KNOWLEDGE_STATUS_NEW as SERVICES_STATUS_NEW,
        )
        assert MODELS_STATUS_NEW == SERVICES_STATUS_NEW == "NEW"
        assert MODELS_VALID_STATUSES is SERVICES_VALID_STATUSES

    def test_legacy_archived_is_normalized_before_filtering(
        self, tmp_path: Path
    ) -> None:
        """KI-009: lowercase persisted ARCHIVED cannot leak into retrieval."""
        fx = ContractFixture(tmp_path)
        pid = fx.project()
        knowledge = fx.register(pid, "legacy archived")
        path = fx.engine.path_manager.knowledge_file(
            fx.engine.root, pid, knowledge.id)
        doc = fx.engine.read_json(path)
        doc["data"]["status"] = "archived"
        fx.engine.write_json(path, doc)

        loaded = fx.repos.knowledge.load(pid, knowledge.id)
        ranked = RankedCandidate(
            entity=loaded, entity_type="knowledge", score=1.0,
            factors={}, sources=[])

        assert loaded.status == KNOWLEDGE_STATUS_ARCHIVED
        assert KnowledgeFilter.filter([ranked]) == []


class TestRepositoryBoundary:
    """Target: repository exposes no lifecycle mutations."""

    def test_repository_has_no_lifecycle_mutation(self, tmp_path: Path) -> None:
        """KI-006: the repository API exposes no archive() mutation.

        Lifecycle transitions belong to the Librarian; the repository layer
        must not offer a status-mutating method.
        """
        fx = ContractFixture(tmp_path)
        assert not hasattr(fx.repos.knowledge, "archive")

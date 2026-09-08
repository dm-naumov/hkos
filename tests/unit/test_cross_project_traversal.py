"""IP-017-v1.2 ЭТАП 4: кросс-проектный обход графа (DS-017 v1.2).

Связи с target_project_id обходятся через снапшоты целевых проектов:
retrieve(B) возвращает связанное знание проекта A как relation-кандидата.
"""

from __future__ import annotations

from pathlib import Path

from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.index import IndexCache, IndexEngine, IndexQueryExecutor, IndexStore
from hkos.repository.models import Knowledge
from hkos.repository.knowledge_relations import KnowledgeRelation, RelationType
from hkos.repository.repository_manager import RepositoryManager
from hkos.retrieval import RetrievalEngine
from hkos.retrieval.relationship_traverser import RelationshipTraverser
from hkos.services.librarian import Librarian
from hkos.services.project_manager import ProjectManager
from hkos.storage import StorageEngine


class CrossProjectFixture:
    """Композиция: проект A (факт) + проект B (решение ссылается на A)."""

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
        self.qc = qc

    def seed(self) -> tuple[str, str]:
        """Факт в A; решение в B с кросс-рёбрами CAUSED_BY на факт A."""
        a_pid = self.projects.create(name="ProjectA", tags=["a"]).id
        b_pid = self.projects.create(name="ProjectB", tags=["b"]).id
        fact = self.librarian.register(
            a_pid, Knowledge(
                title="tcp window scaling breaks nat", body="fact about mtu",
                tags=["mtu"]))
        self.index.build(a_pid)
        self.librarian.register(
            b_pid, Knowledge(
                title="disable tcp window scaling",
                body="decision fixes mtu issue",
                kind="decision",
                relations=[KnowledgeRelation(
                    relation_type=RelationType.CAUSED_BY,
                    source_id="",  # Librarian проставит источник (владельца)
                    target_id=fact.id,
                    target_project_id=a_pid,
                )]))
        self.index.build(b_pid)
        return a_pid, b_pid


class TestCrossProjectTraversal:
    """ЭТАП 4: кросс-проектные связи в traverser и retrieve."""

    def test_traverser_reaches_cross_project_target(
        self, tmp_path: Path
    ) -> None:
        """traverse с provider: цель из другого проекта загружается."""
        fx = CrossProjectFixture(tmp_path)
        a_pid, b_pid = fx.seed()
        snapshot_b = fx.qc.snapshot(b_pid)
        b_knowledge = fx.repos.knowledge.list(b_pid)
        assert b_knowledge
        from hkos.retrieval.ranking_engine import RankedCandidate

        seed = RankedCandidate(
            entity=b_knowledge[0], entity_type="knowledge", score=1.0,
            factors={}, sources=["topic"],
        )
        # без provider: кросс-цель недоступна (как раньше)
        solo = RelationshipTraverser(fx.repos).traverse(
            [seed], b_pid, snapshot_b)
        assert len(solo) == 1
        # с provider: факт проекта A приходит как relation-кандидат
        crossed = RelationshipTraverser(fx.repos).traverse(
            [seed], b_pid, snapshot_b, snapshot_provider=fx.qc.snapshot)
        assert len(crossed) == 2, [c.entity.title for c in crossed]
        added = crossed[1]
        assert added.entity.title == "tcp window scaling breaks nat"
        assert added.sources == ["relation"]
        assert added.relation_path and added.relation_path[0]

    def test_retrieve_includes_cross_project_related(
        self, tmp_path: Path
    ) -> None:
        """retrieve(B) по слову факта: знание A приходит связанным."""
        fx = CrossProjectFixture(tmp_path)
        a_pid, b_pid = fx.seed()
        result = fx.retrieval.retrieve("window scaling", project_id=b_pid,
                                       top_n=5)
        titles = [item.entity.title for item in result.items]
        assert "disable tcp window scaling" in titles
        # поиск без обхода связей факт A не возвращает (нет общего токена
        # в B-кандидатах) — контрпример для search()
        searched = fx.retrieval.search("window scaling", project_id=b_pid,
                                       top_n=5)
        searched_titles = [item.entity.title for item in searched.items]
        assert "tcp window scaling breaks nat" not in searched_titles
        assert "tcp window scaling breaks nat" in titles

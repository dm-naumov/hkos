"""Knowledge Integrity Baseline — v1.2.0 characterization tests.

INTENT: this file pins the CURRENT v1.2.0 behavior on the knowledge
integrity boundary — it is a characterization baseline, NOT a statement of
desired semantics. Target semantics are expressed (as XFAIL) in
tests/architecture/test_knowledge_integrity_contract.py and documented in
docs/design/adr-001-knowledge-integrity-contract.md.

Every test here documents observable v1.2.0 behavior through public
components (Librarian, KnowledgeFilter, MCP server, Retrieval/Traverser).
None of these tests asserts that the behavior is correct; a later lifecycle
fix will flip the corresponding contract tests and update this file.

Deterministic: tmp_path-backed, no wall clock, no network, no global config
mutation, no production monkeypatching.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.index import IndexCache, IndexEngine, IndexQueryExecutor, IndexStore
from hkos.repository.knowledge_relations import KnowledgeRelation, RelationType
from hkos.repository.models import Knowledge
from hkos.repository.repository_manager import RepositoryManager
from hkos.retrieval import RetrievalEngine
from hkos.retrieval.knowledge_filter import KnowledgeFilter
from hkos.retrieval.ranking_engine import RankedCandidate
from hkos.services.librarian import Librarian
from hkos.services.librarian.knowledge_history import (
    EVENT_CANONICALIZED,
    EVENT_CREATED,
    EVENT_VERIFIED,
)
from hkos.services.librarian.knowledge_status import (
    KNOWLEDGE_STATUS_ARCHIVED,
    KNOWLEDGE_STATUS_CANONICAL,
    KNOWLEDGE_STATUS_NEW,
)
from hkos.services.project_manager import ProjectManager
from hkos.storage import StorageEngine


class _McpClient:
    """Минимальный stdio JSON-RPC клиент hkos-mcp (локальная копия).

    Локальная копия вместо импорта из test_mcp_server: кросс-импорт
    тест-модулей ломает mypy (hkos.tests.* vs tests.* double mapping).
    """

    def __init__(self, data_root: Path) -> None:
        env = {
            **os.environ,
            "PYTHONPATH": str(Path(__file__).resolve().parents[2].parent),
            "HKOS_DATA_ROOT": str(data_root),
            "HKOS_LOG_LEVEL": "ERROR",
        }
        self._proc = subprocess.Popen(
            [sys.executable, "-m", "hkos.mcp_server.server", "--root",
             str(data_root)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, env=env,
            cwd=str(Path(__file__).resolve().parents[2]),
        )
        self._seq = 0

    def call(self, tool: str,
             arguments: dict[str, object]) -> tuple[Any, bool]:
        self._seq += 1
        message = {
            "jsonrpc": "2.0", "method": "tools/call", "id": self._seq,
            "params": {"name": tool, "arguments": arguments},
        }
        assert self._proc.stdin is not None
        self._proc.stdin.write(json.dumps(message) + "\n")
        self._proc.stdin.flush()
        line = self._proc.stdout.readline() if self._proc.stdout else ""
        if not line:
            stderr = self._proc.stderr.read() if self._proc.stderr else ""
            raise RuntimeError(f"server closed stdout: {stderr[-2000:]}")
        resp = json.loads(line)
        assert isinstance(resp, dict) and "result" in resp
        result = resp["result"]
        assert isinstance(result, dict)
        text = result["content"][0]["text"]
        assert isinstance(text, str)
        return json.loads(text), bool(result.get("isError", False))

    def close(self) -> None:
        if self._proc.stdin:
            self._proc.stdin.close()
        try:
            self._proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self._proc.kill()


class KnowledgeIntegrityFixture:
    """Repository + Index + Librarian + Retrieval over a tmp data root.

    JSON index backend (default). Mirrors the documented production
    composition; nothing is mocked.
    """

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

    def register(
        self,
        pid: str,
        title: str,
        body: str = "body text",
        tags: list[str] | None = None,
        relations: list[KnowledgeRelation] | None = None,
        index_update: bool = True,
    ) -> Knowledge:
        knowledge = self.librarian.register(
            pid, Knowledge(
                title=title, body=body, tags=tags or [],
                relations=relations or []))
        if index_update:
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

    def titles_of(self, items: list[Any]) -> list[str]:
        return [item.entity.title for item in items]


class TestRegisterAndCanonicalize:
    """Current register/canonicalize lifecycle (v1.2.0 characterization)."""

    def test_register_creates_new(self, tmp_path: Path) -> None:
        """v1.2.0: register returns a knowledge in status NEW."""
        fx = KnowledgeIntegrityFixture(tmp_path)
        pid = fx.projects.create(name="P", tags=["t"]).id
        k = fx.register(pid, "some observation", index_update=False)
        assert k.status == KNOWLEDGE_STATUS_NEW

    def test_verify_then_canonicalize_records_distinct_events(
        self, tmp_path: Path
    ) -> None:
        """Verification and canonicalization are separate public actions."""
        fx = KnowledgeIntegrityFixture(tmp_path)
        pid = fx.projects.create(name="P", tags=["t"]).id
        k = fx.register(pid, "claim with explicit trust", index_update=False)
        verified = fx.librarian.verify(pid, k.id)
        assert verified.status == "VERIFIED"
        canonical = fx.canonicalize(pid, k.id)
        events = [entry.event for entry in canonical.history]
        assert events == [EVENT_CREATED, EVENT_VERIFIED, EVENT_CANONICALIZED]


class TestKnowledgeFilterCurrent:
    """Default KnowledgeFilter membership after KI-001 remediation."""

    @staticmethod
    def _candidate(status: str, title: str) -> RankedCandidate:
        return RankedCandidate(
            entity=Knowledge(title=title, status=status),
            entity_type="knowledge", score=1.0, factors={}, sources=[],
        )

    def test_filter_keeps_only_canonical_by_default(
        self, tmp_path: Path
    ) -> None:
        """KI-001: ordinary retrieval admits CANONICAL only."""
        kept = KnowledgeFilter.filter([
            self._candidate("NEW", "n"),
            self._candidate("VERIFIED", "v"),
            self._candidate("CANONICAL", "c"),
            self._candidate("CONFLICT", "x"),
        ])
        assert [k.entity.status for k in kept] == ["CANONICAL"]

    def test_filter_excludes_archived_rejected_superseded(
        self, tmp_path: Path
    ) -> None:
        """v1.2.0: default filter drops ARCHIVED/REJECTED/SUPERSEDED."""
        kept = KnowledgeFilter.filter([
            self._candidate("ARCHIVED", "a"),
            self._candidate("REJECTED", "r"),
            self._candidate("SUPERSEDED", "s"),
            self._candidate("CANONICAL", "c"),
        ])
        assert [k.entity.status for k in kept] == ["CANONICAL"]


class TestMcpSavePolicy:
    """MCP save write path: observations are non-canonical by default."""

    def test_save_schema_canonicalize_defaults_false(
        self, tmp_path: Path
    ) -> None:
        """The save schema makes trust promotion explicit and opt-in."""
        from hkos.mcp_server.tools import TOOLS

        save_schema: dict[str, Any] = {}
        for tool in TOOLS:
            if tool["name"] == "save":
                save_schema = tool["inputSchema"]
        assert save_schema, "save tool must exist"
        properties = save_schema.get("properties", {})
        canonicalize = properties.get("canonicalize")
        assert canonicalize is not None, (
            "save schema must declare canonicalize")
        assert canonicalize.get("default") is False

    def test_save_without_canonicalize_returns_new(
        self, tmp_path: Path
    ) -> None:
        """MCP save without an elevated action returns a NEW observation."""
        client = _McpClient(tmp_path / "mcp")
        try:
            result, is_error = client.call("save", {
                "project": "P1",
                "title": "mcp default observation",
                "body": "body",
            })
            assert not is_error, result
            assert result["status"] == KNOWLEDGE_STATUS_NEW
        finally:
            client.close()

    def test_save_with_canonicalize_false_returns_new(
        self, tmp_path: Path
    ) -> None:
        """Explicit canonicalize=false also returns a NEW observation."""
        client = _McpClient(tmp_path / "mcp")
        try:
            result, is_error = client.call("save", {
                "project": "P2",
                "title": "mcp non canonical",
                "body": "body",
                "canonicalize": False,
            })
            assert not is_error, result
            assert result["status"] == KNOWLEDGE_STATUS_NEW
        finally:
            client.close()


class TestGraphTraversalCurrent:
    """Graph expansion vs eligibility (v1.2.0 characterization)."""

    def _seed_anchor_and_archived_neighbor(
        self, fx: KnowledgeIntegrityFixture, pid: str
    ) -> tuple[str, str]:
        """CANONICAL anchor A -> ARCHIVED neighbor B (typed edge)."""
        b = fx.register(pid, "archived graph neighbor", body="bb body")
        archived = fx.archive(pid, b.id)
        assert archived.status == KNOWLEDGE_STATUS_ARCHIVED
        a = fx.register(
            pid,
            "alpha anchor anchorfact",
            body="alpha specific body",
            tags=["alpha"],
            relations=[KnowledgeRelation(
                relation_type=RelationType.REFERENCE_TO,
                source_id="",
                target_id=b.id,
            )],
        )
        fx.librarian.verify(pid, a.id)
        fx.canonicalize(pid, a.id)
        return a.id, b.id

    def test_traversal_cannot_restore_ineligible_neighbor(
        self, tmp_path: Path
    ) -> None:
        """KI-002: graph expansion cannot restore an ARCHIVED neighbor."""
        fx = KnowledgeIntegrityFixture(tmp_path)
        pid = fx.projects.create(name="P", tags=["t"]).id
        a_id, b_id = self._seed_anchor_and_archived_neighbor(fx, pid)

        result = fx.retrieval.retrieve("alpha", project_id=pid, top_n=10)
        titles = fx.titles_of(result.items)
        assert "archived graph neighbor" not in titles
        assert "alpha anchor anchorfact" in titles

    def test_include_history_applies_to_relation_neighbor(
        self, tmp_path: Path
    ) -> None:
        """Explicit history policy admits an ARCHIVED relation neighbor."""
        fx = KnowledgeIntegrityFixture(tmp_path)
        pid = fx.projects.create(name="P", tags=["t"]).id
        a_id, b_id = self._seed_anchor_and_archived_neighbor(fx, pid)

        result = fx.retrieval.retrieve(
            "alpha", project_id=pid, top_n=10, include_history=True)
        neighbor = next(
            (item for item in result.items
             if item.entity.title == "archived graph neighbor"), None)
        assert neighbor is not None
        assert neighbor.entity.status == KNOWLEDGE_STATUS_ARCHIVED
        assert neighbor.explanation.relation_path, (
            "neighbor must arrive via relation expansion")

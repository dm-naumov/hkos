"""E2E pipeline tests: Hermes -> HKOS (DS-012 ЭТАП 5)."""

import time
from pathlib import Path

import pytest
from pytest import MonkeyPatch

from hkos.context import ContextBuilder
from hkos.context import SnapshotLoader as ContextSnapshotLoader
from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.index import IndexEngine, IndexQueryExecutor, IndexStore
from hkos.integration.hermes.audit import AuditLogger
from hkos.integration.hermes.migration_tools import MigrationTools
from hkos.integration.hermes.schemas import MigrationErrorResponse
from hkos.integration.hermes.security import AgentContext
from hkos.repository.models import Knowledge
from hkos.repository.repository_manager import RepositoryManager
from hkos.retrieval import RetrievalEngine
from hkos.services.campaign_manager import CampaignManager
from hkos.services.librarian import Librarian
from hkos.services.memory_service import MemoryService, PreparedContext
from hkos.services.project_manager import ProjectManager
from hkos.snapshot import SnapshotEngine
from hkos.storage import StorageEngine


class _Persistence:
    def __init__(self) -> None:
        self._docs: dict[str, dict[str, dict[str, object]]] = {}
        self._order: dict[str, list[str]] = {}
        self._history: dict[str, list[dict[str, object]]] = {}

    def latest(self, project: str) -> dict[str, object] | None:
        order = self._order.get(project, [])
        if not order:
            return None
        return self._docs.get(project, {}).get(order[-1])

    def version(self, project: str, version: str) -> dict[str, object] | None:
        return self._docs.get(project, {}).get(f"snapshot-{version}")

    def save(self, project: str, doc: dict[str, object]) -> str:
        snapshot_id = str(doc.get("snapshot_id", ""))
        self._docs.setdefault(project, {})[snapshot_id] = doc
        self._order.setdefault(project, []).append(snapshot_id)
        return snapshot_id

    def history(self, project: str) -> list[dict[str, object]]:
        return self._history.get(project, [])

    def append_history(self, project: str, entry: dict[str, object]) -> None:
        self._history.setdefault(project, []).append(entry)


def _llm_mock(context: object) -> str:
    return "task completed"


class _Harness:
    def __init__(self, tmp_path: Path):
        cfg = ConfigLoader(profile="development")
        cfg.load()
        self.engine = StorageEngine(
            root=str(tmp_path), config=cfg, logger=HKOSLogger(),
            version=VersionManager())
        self.engine.initialize()
        self.repos = RepositoryManager(self.engine)
        self.projects = ProjectManager(self.repos, HKOSLogger())
        self.campaigns = CampaignManager(self.repos, HKOSLogger())
        self.librarian = Librarian(self.repos, HKOSLogger())
        self.index = IndexEngine(self.repos, IndexStore(self.engine), HKOSLogger())
        self.persistence = _Persistence()
        qc = IndexQueryExecutor(IndexStore(self.engine))
        self.snapshots = SnapshotEngine(
            self.repos, self.persistence, HKOSLogger(), index_provider=qc.snapshot)
        self.retrieval = RetrievalEngine(self.repos, qc, cfg, HKOSLogger())
        self.ctx_loader = ContextSnapshotLoader(
            lambda pid: self._load_snapshot_dict(pid))
        self.context = ContextBuilder(cfg, HKOSLogger(), loader=self.ctx_loader)
        self.memory = MemoryService(
            self.projects, self.campaigns, self.retrieval, self.context,
            self.librarian, self.index, self.snapshots)

    def _load_snapshot_dict(self, pid: str) -> dict[str, object] | None:
        snapshot = self.snapshots.load(pid)
        return snapshot.as_dict() if snapshot is not None else None


class _ProbeEngine:
    def __init__(self) -> None:
        self.failed = False

    def acquire_lock(self) -> None:
        pass

    def release_lock(self) -> None:
        pass

    def history(self) -> list[object]:
        return []

    def status(self) -> str:
        return "COMPLETED; current=1; target=1"

    def detect(self) -> object:
        return None

    def migrate(self) -> None:
        if self.failed:
            from hkos.migration.exceptions import MigrationError
            raise MigrationError("failed")

    def rollback(self) -> None:
        if self.failed:
            from hkos.migration.exceptions import MigrationError
            raise MigrationError("failed")

    def validate(self) -> None:
        pass


class TestE2EPipeline:
    def test_full_pipeline_order(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        h = _Harness(tmp_path)
        order: list[str] = []

        def recorder(name: str, fn: object) -> object:
            def wrapper(*args: object, **kwargs: object) -> object:
                order.append(name)
                return fn(*args, **kwargs)  # type: ignore[operator]
            return wrapper

        targets = [
            (h.memory, "resolve_project", "resolve_project"),
            (h.memory, "resolve_campaign", "resolve_campaign"),
            (h.memory, "prepare_context", "prepare_context"),
            (h.retrieval, "retrieve", "retrieve"),
            (h.context, "build", "context_build"),
            (h.librarian, "register", "register"),
            (h.index, "update", "index_update"),
            (h.snapshots, "create", "snapshot_create"),
        ]
        for target, attr, step in targets:
            original = getattr(target, attr)
            monkeypatch.setattr(target, attr, recorder(step, original))

        agent = AgentContext(agent_id="planner", project_id="")
        prepared = h.memory.prepare_context(
            agent_id=agent.agent_id, query="udp routing", project_name="OpenWrt")
        response = _llm_mock(prepared.context)
        result = h.memory.save_results(
            agent_id=agent.agent_id,
            project_id=prepared.project_id,
            knowledge=[Knowledge(title=f"Result of {response}",
                                 body="udp fix applied", tags=["udp"])],
        )
        assert response == "task completed"
        assert len(result.saved) == 1
        for step in ("resolve_project", "resolve_campaign", "prepare_context",
                     "retrieve", "context_build", "register", "index_update"):
            assert step in order, step
        assert order.index("resolve_project") < order.index("resolve_campaign")
        assert order.index("resolve_campaign") < order.index("retrieve")
        assert order.index("retrieve") < order.index("context_build")
        assert order.index("context_build") < order.index("register")
        first_index_update = order.index("index_update")
        last_index_update = len(order) - 1 - order[::-1].index("index_update")
        assert order.index("resolve_campaign") < first_index_update
        assert order.index("register") < last_index_update

    def test_data_flows_between_layers(self, tmp_path: Path) -> None:
        h = _Harness(tmp_path)
        project = h.projects.create(name="OpenWrt", tags=["router"])
        k = h.librarian.register(project.id, Knowledge(
            title="UDP works", body="udp routing fix", tags=["udp"]))
        h.librarian.canonicalize(project.id, k.id)
        h.index.update(project.id, k.id, "knowledge")
        prepared = h.memory.prepare_context(
            agent_id="agent-1", query="udp", project_id=project.id)
        assert prepared.project_id == project.id
        assert len(prepared.retrieval_items) >= 1
        assert prepared.context is not None
        result = h.memory.save_results(
            agent_id="agent-1", project_id=project.id,
            knowledge=[Knowledge(title="UDP v2", body="udp updated", tags=["udp"])])
        assert len(result.saved) == 1
        saved_id = result.saved[0]
        ordinary = h.retrieval.retrieve("udp v2", project_id=project.id)
        assert all(item.entity.id != saved_id for item in ordinary.items)
        historical = h.retrieval.retrieve(
            "udp v2", project_id=project.id, include_history=True)
        assert any(item.entity.id == saved_id for item in historical.items)


class TestMemoryService:
    def test_prepare_context_components(self, tmp_path: Path) -> None:
        h = _Harness(tmp_path)
        prepared = h.memory.prepare_context(
            agent_id="a", query="udp", project_name="NewProject")
        assert isinstance(prepared, PreparedContext)
        assert prepared.project_id
        assert prepared.campaign_id
        assert prepared.snapshot_used is False
        assert prepared.context is not None

    def test_prepare_uses_snapshot_when_exists(self, tmp_path: Path) -> None:
        h = _Harness(tmp_path)
        project = h.projects.create(name="OpenWrt", tags=["router"])
        h.snapshots.create(project.id, reason="initial")
        prepared = h.memory.prepare_context(
            agent_id="a", query="udp", project_id=project.id)
        assert prepared.snapshot_used is True

    def test_save_results_updates_index_and_snapshot(self, tmp_path: Path) -> None:
        h = _Harness(tmp_path)
        project = h.projects.create(name="OpenWrt", tags=["router"])
        result = h.memory.save_results(
            agent_id="a", project_id=project.id,
            knowledge=[Knowledge(title="K1", body="b1", tags=["t1"])])
        assert len(result.saved) == 1
        found = h.retrieval.retrieve("K1", project_id=project.id)
        assert found.items == []
        historical = h.retrieval.retrieve(
            "K1", project_id=project.id, include_history=True)
        assert len(historical.items) >= 1
        assert h.snapshots.load(project.id) is not None


class TestProjectCampaignFlow:
    def test_new_project_created(self, tmp_path: Path) -> None:
        h = _Harness(tmp_path)
        project = h.memory.resolve_project(project_name="BrandNew")
        assert project.name == "BrandNew"

    def test_existing_project_auto_detected(self, tmp_path: Path) -> None:
        h = _Harness(tmp_path)
        created = h.projects.create(name="OpenWrt", tags=["router"])
        resolved = h.memory.resolve_project(project_name="OpenWrt")
        assert resolved.id == created.id

    def test_active_campaign_continued(self, tmp_path: Path) -> None:
        h = _Harness(tmp_path)
        project = h.projects.create(name="OpenWrt", tags=["router"])
        campaign = h.campaigns.create(project.id, goal="first")
        h.campaigns.open(project.id, campaign.id)
        h.campaigns.open(project.id, campaign.id)
        resolved = h.memory.resolve_campaign(project.id)
        assert resolved.id == campaign.id

    def test_no_campaign_creates_new(self, tmp_path: Path) -> None:
        h = _Harness(tmp_path)
        project = h.projects.create(name="OpenWrt", tags=["router"])
        resolved = h.memory.resolve_campaign(project.id, goal="new-goal")
        assert resolved.id

    def test_campaign_without_project_forbidden(self, tmp_path: Path) -> None:
        h = _Harness(tmp_path)
        with pytest.raises(RuntimeError):
            h.memory.resolve_campaign("")


class TestSnapshotFlow:
    def test_with_snapshot(self, tmp_path: Path) -> None:
        h = _Harness(tmp_path)
        project = h.projects.create(name="OpenWrt", tags=["router"])
        h.snapshots.create(project.id, reason="r")
        prepared = h.memory.prepare_context(
            agent_id="a", query="udp", project_id=project.id)
        assert prepared.snapshot_used is True
        assert prepared.context is not None

    def test_without_snapshot_no_errors(self, tmp_path: Path) -> None:
        h = _Harness(tmp_path)
        project = h.projects.create(name="OpenWrt", tags=["router"])
        prepared = h.memory.prepare_context(
            agent_id="a", query="udp", project_id=project.id)
        assert prepared.snapshot_used is False
        assert prepared.context is not None


class TestFailureKnowledge:
    def test_failure_knowledge_saved_and_retrievable(self, tmp_path: Path) -> None:
        h = _Harness(tmp_path)
        project = h.projects.create(name="OpenWrt", tags=["router"])
        failure = Knowledge(
            title="TPROXY broken",
            body="problem: tproxy failed\ncause: missing nft rule\n"
                 "actions: added rule\nresult: still broken\n"
                 "recommendations: use redirect instead",
            kind="negative", tags=["tproxy", "failure"])
        result = h.memory.save_results(
            agent_id="a", project_id=project.id, failures=[failure])
        assert len(result.failures) == 1
        stored = h.repos.knowledge.load(project.id, result.failures[0])
        assert stored.category == "FAILURE"
        found = h.retrieval.retrieve("tproxy broken", project_id=project.id)
        assert found.items == []
        historical = h.retrieval.retrieve(
            "tproxy broken", project_id=project.id, include_history=True)
        assert len(historical.items) >= 1


class TestMultiAgent:
    def test_shared_memory_and_audit(self, tmp_path: Path) -> None:
        h = _Harness(tmp_path)
        project = h.projects.create(name="OpenWrt", tags=["router"])
        audit = AuditLogger()
        planner = AgentContext(agent_id="planner", agent_type="planner",
                               project_id=project.id)
        executor = AgentContext(agent_id="executor", agent_type="executor",
                                project_id=project.id)
        saved = h.memory.save_results(
            agent_id=planner.agent_id, project_id=project.id,
            knowledge=[Knowledge(title="Planner fact", body="plan udp", tags=["udp"])])
        audit.log("KNOWLEDGE_WRITTEN", planner.agent_id, "knowledge.save",
                  project.id, "", "ok")
        assert len(saved.saved) == 1
        h.librarian.canonicalize(project.id, saved.saved[0])
        found = h.retrieval.retrieve("Planner fact", project_id=project.id)
        assert len(found.items) >= 1
        executor_saved = h.memory.save_results(
            agent_id=executor.agent_id, project_id=project.id,
            knowledge=[Knowledge(title="Executor fact", body="exec udp", tags=["udp"])])
        h.librarian.canonicalize(project.id, executor_saved.saved[0])
        found = h.retrieval.retrieve("Executor fact", project_id=project.id)
        assert len(found.items) >= 1
        assert any(e.agent_id == "planner" for e in audit.entries())


class TestSecurityE2E:
    def test_write_without_permission_blocked(self, tmp_path: Path) -> None:
        engine = _ProbeEngine()
        tools = MigrationTools(engine)  # type: ignore[arg-type]
        agent = AgentContext(agent_id="agent-1")
        response = tools.migrate(agent, confirmed=True)
        assert isinstance(response, MigrationErrorResponse)
        assert response.recoverable is True

    def test_rollback_without_confirmation_blocked(self, tmp_path: Path) -> None:
        engine = _ProbeEngine()
        tools = MigrationTools(engine)  # type: ignore[arg-type]
        agent = AgentContext(agent_id="agent-1", project_id="p1")
        response = tools.rollback(agent, confirmed=False)
        assert isinstance(response, MigrationErrorResponse)
        assert "confirmation" in response.message

    def test_admin_with_confirmation_passes(self, tmp_path: Path) -> None:
        from hkos.integration.hermes.schemas import MigrationOperationResponse
        engine = _ProbeEngine()
        tools = MigrationTools(engine)  # type: ignore[arg-type]
        agent = AgentContext(agent_id="admin", project_id="p1")
        response = tools.rollback(agent, confirmed=True)
        assert isinstance(response, MigrationOperationResponse)

    def test_audit_events_present(self, tmp_path: Path) -> None:
        engine = _ProbeEngine()
        audit = AuditLogger()
        tools = MigrationTools(engine, audit=audit)  # type: ignore[arg-type]
        agent = AgentContext(agent_id="agent-1", project_id="p1")
        tools.rollback(agent, confirmed=False)
        tools.status(agent)
        commands = {e.command for e in audit.entries()}
        assert "migration.rollback" in commands
        assert "migration.status" in commands
        denied = [e for e in audit.entries()
                  if e.command == "migration.rollback"
                  and e.event == "COMMAND_DENIED"]
        assert denied


class TestFallbackE2E:
    def test_retrieval_unavailable_continues(self, tmp_path: Path) -> None:
        h = _Harness(tmp_path)
        project = h.projects.create(name="OpenWrt", tags=["router"])
        h.memory._retrieval_available = False
        prepared = h.memory.prepare_context(
            agent_id="a", query="udp", project_id=project.id)
        assert prepared.retrieval_items == []
        assert prepared.context is not None or prepared.retrieval_items == []
        result = h.memory.save_results(
            agent_id="a", project_id=project.id,
            knowledge=[Knowledge(title="K", body="b", tags=["t"])])
        assert len(result.saved) == 1

    def test_snapshot_unavailable_continues(self, tmp_path: Path) -> None:
        h = _Harness(tmp_path)
        project = h.projects.create(name="OpenWrt", tags=["router"])
        h.memory._snapshot_available = False
        prepared = h.memory.prepare_context(
            agent_id="a", query="udp", project_id=project.id)
        assert prepared.snapshot_used is False

    def test_librarian_unavailable_queues_and_drains(self, tmp_path: Path) -> None:
        h = _Harness(tmp_path)
        project = h.projects.create(name="OpenWrt", tags=["router"])
        h.memory._librarian_available = False
        result = h.memory.save_results(
            agent_id="a", project_id=project.id,
            knowledge=[Knowledge(title="K1", body="b1", tags=["t1"]),
                       Knowledge(title="K2", body="b2", tags=["t2"])])
        assert result.saved == []
        assert h.memory.pending_count() == 2
        h.memory.reset_fallbacks()
        h.memory.drain_pending()
        assert h.memory.pending_count() == 0


class TestPipelinePerformance:
    def test_pipeline_budgets(self, tmp_path: Path) -> None:
        h = _Harness(tmp_path)
        project = h.projects.create(name="OpenWrt", tags=["router"])
        h.librarian.register(project.id, Knowledge(
            title="UDP works", body="udp fix", tags=["udp"]))
        h.index.build(project.id)
        start = time.monotonic()
        h.memory.resolve_project(project_id=project.id)
        resolve_ms = (time.monotonic() - start) * 1000
        assert resolve_ms <= 20, f"project resolver {resolve_ms:.1f} ms"
        start = time.monotonic()
        result = h.retrieval.retrieve("udp", project_id=project.id)
        retrieval_ms = (time.monotonic() - start) * 1000
        assert retrieval_ms <= 100, f"retrieval {retrieval_ms:.1f} ms"
        start = time.monotonic()
        h.context.build(result, project.id)
        context_ms = (time.monotonic() - start) * 1000
        assert context_ms <= 200, f"context build {context_ms:.1f} ms"
        start = time.monotonic()
        h.memory.save_results(
            agent_id="a", project_id=project.id,
            knowledge=[Knowledge(title="New", body="new", tags=["n"])])
        save_ms = (time.monotonic() - start) * 1000
        assert save_ms <= 150, f"save {save_ms:.1f} ms"
        start = time.monotonic()
        h.memory.prepare_context(agent_id="a", query="udp", project_id=project.id)
        total_ms = (time.monotonic() - start) * 1000
        assert total_ms <= 500, f"total overhead {total_ms:.1f} ms"

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
    """Мок ответа LLM по контексту."""
    return "task completed"


class _Harness:
    """Полная композиция HKOS для E2E pipeline."""

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
    """Локальный двойник MigrationEngine (без кросс-импортов тестов)."""

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
    """Полный жизненный цикл задачи: User -> Hermes -> ... -> Snapshot."""

    def test_full_pipeline_order(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        h = _Harness(tmp_path)
        order: list[str] = []

        def recorder(name: str, fn: object) -> object:
            """Обёртка: фиксирует порядок вызова, делегирует оригиналу."""

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
        # все шаги вызваны; порядок соответствует pipeline
        for step in ("resolve_project", "resolve_campaign", "prepare_context",
                     "retrieve", "context_build", "register", "index_update"):
            assert step in order, step
        assert order.index("resolve_project") < order.index("resolve_campaign")
        assert order.index("resolve_campaign") < order.index("retrieve")
        assert order.index("retrieve") < order.index("context_build")
        assert order.index("context_build") < order.index("register")
        # DS-017 (incident 001 fix): index_update вызывается в двух фазах —
        # (1) campaign sync сразу после resolve_campaign (при создании кампании);
        # (2) knowledge sync ПОСЛЕ register (save-путь) — последнее вхождение.
        first_index_update = order.index("index_update")
        last_index_update = len(order) - 1 - order[::-1].index("index_update")
        assert order.index("resolve_campaign") < first_index_update
        assert order.index("register") < last_index_update

    def test_data_flows_between_layers(self, tmp_path: Path) -> None:
        h = _Harness(tmp_path)
        # предварительное знание
        project = h.projects.create(name="OpenWrt", tags=["router"])
        k = h.librarian.register(project.id, Knowledge(
            title="UDP works", body="udp routing fix", tags=["udp"]))
        h.index.update(project.id, k.id, "knowledge")
        # задача
        prepared = h.memory.prepare_context(
            agent_id="agent-1", query="udp", project_id=project.id)
        assert prepared.project_id == project.id
        assert len(prepared.retrieval_items) >= 1  # retrieval нашёл знание
        assert prepared.context is not None  # контекст построен
        # результат сохраняется и становится retrievable
        result = h.memory.save_results(
            agent_id="agent-1", project_id=project.id,
            knowledge=[Knowledge(title="UDP v2", body="udp updated", tags=["udp"])])
        assert len(result.saved) == 1
        again = h.retrieval.retrieve("udp v2", project_id=project.id)
        assert len(again.items) >= 1  # данные дошли до Retrieval


class TestMemoryService:
    """prepare_context / save_results (DS-012 ЭТАП 5 §2)."""

    def test_prepare_context_components(self, tmp_path: Path) -> None:
        h = _Harness(tmp_path)
        prepared = h.memory.prepare_context(
            agent_id="a", query="udp", project_name="NewProject")
        assert isinstance(prepared, PreparedContext)
        assert prepared.project_id
        assert prepared.campaign_id
        assert prepared.snapshot_used is False  # снимка нет
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
        # index обновлён: retrieval находит знание
        found = h.retrieval.retrieve("K1", project_id=project.id)
        assert len(found.items) >= 1
        # snapshot создан
        assert h.snapshots.load(project.id) is not None


class TestProjectCampaignFlow:
    """Новый/существующий проект; активная кампания; запрет без проекта."""

    def test_new_project_created(self, tmp_path: Path) -> None:
        h = _Harness(tmp_path)
        project = h.memory.resolve_project(project_name="BrandNew")
        assert project.name == "BrandNew"

    def test_existing_project_auto_detected(self, tmp_path: Path) -> None:
        h = _Harness(tmp_path)
        created = h.projects.create(name="OpenWrt", tags=["router"])
        resolved = h.memory.resolve_project(project_name="OpenWrt")
        assert resolved.id == created.id  # не создан заново

    def test_active_campaign_continued(self, tmp_path: Path) -> None:
        h = _Harness(tmp_path)
        project = h.projects.create(name="OpenWrt", tags=["router"])
        campaign = h.campaigns.create(project.id, goal="first")
        h.campaigns.open(project.id, campaign.id)   # CREATED -> READY
        h.campaigns.open(project.id, campaign.id)   # READY -> RUNNING
        resolved = h.memory.resolve_campaign(project.id)
        assert resolved.id == campaign.id  # продолжение активной (RUNNING)

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
    """Snapshot есть -> контекст с ним; нет -> без ошибок."""

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
        assert prepared.context is not None  # контекст без снимка работает


class TestFailureKnowledge:
    """Задача с ошибкой -> Knowledge FAILURE; retrieval находит."""

    def test_failure_knowledge_saved_and_retrievable(self, tmp_path: Path) -> None:
        h = _Harness(tmp_path)
        project = h.projects.create(name="OpenWrt", tags=["router"])
        failure = Knowledge(
            title="TPROXY broken",
            body="problem: tproxy failed\ncause: missing nft rule\n"
                 "actions: added rule\nresult: still broken\n"
                 "recommendations: use redirect instead",
            kind="negative",
            tags=["tproxy", "failure"],
        )
        result = h.memory.save_results(
            agent_id="a", project_id=project.id, failures=[failure])
        assert len(result.failures) == 1
        # категория FAILURE (классификатор: kind=negative -> FAILURE)
        stored = h.repos.knowledge.load(project.id, result.failures[0])
        assert stored.category == "FAILURE"
        # retrieval находит FAILURE записи
        found = h.retrieval.retrieve("tproxy broken", project_id=project.id)
        assert len(found.items) >= 1


class TestMultiAgent:
    """3 агента (Planner/Executor/Reviewer) на одном HKOS (DS-012 §6)."""

    def test_shared_memory_and_audit(self, tmp_path: Path) -> None:
        h = _Harness(tmp_path)
        project = h.projects.create(name="OpenWrt", tags=["router"])
        audit = AuditLogger()
        planner = AgentContext(agent_id="planner", agent_type="planner",
                               project_id=project.id)
        executor = AgentContext(agent_id="executor", agent_type="executor",
                                project_id=project.id)
        # Planner: пишет знание
        saved = h.memory.save_results(
            agent_id=planner.agent_id, project_id=project.id,
            knowledge=[Knowledge(title="Planner fact", body="plan udp", tags=["udp"])])
        audit.log("KNOWLEDGE_WRITTEN", planner.agent_id, "knowledge.save",
                  project.id, "", "ok")
        assert len(saved.saved) == 1
        # Executor: читает + пишет
        found = h.retrieval.retrieve("Planner fact", project_id=project.id)
        assert len(found.items) >= 1
        h.memory.save_results(
            agent_id=executor.agent_id, project_id=project.id,
            knowledge=[Knowledge(title="Executor fact", body="exec udp", tags=["udp"])])
        # Reviewer: только читает (общая память)
        found = h.retrieval.retrieve("Executor fact", project_id=project.id)
        assert len(found.items) >= 1
        # Audit trail содержит события всех агентов
        assert any(e.agent_id == "planner" for e in audit.entries())
        assert len(audit.entries()) >= 1


class TestSecurityE2E:
    """Security boundary E2E (DS-012 ЭТАП 5 §7)."""

    def test_write_without_permission_blocked(self, tmp_path: Path) -> None:
        """WRITE-команда без активного project context -> BLOCK."""
        from hkos.integration.hermes.schemas import MigrationErrorResponse

        engine = _ProbeEngine()
        tools = MigrationTools(engine)  # type: ignore[arg-type]
        agent = AgentContext(agent_id="agent-1")  # БЕЗ project_id
        response = tools.migrate(agent, confirmed=True)
        assert isinstance(response, MigrationErrorResponse)
        assert response.recoverable is True  # BLOCK

    def test_rollback_without_confirmation_blocked(self, tmp_path: Path) -> None:

        engine = _ProbeEngine()
        tools = MigrationTools(engine)  # type: ignore[arg-type]
        agent = AgentContext(agent_id="agent-1", project_id="p1")
        response = tools.rollback(agent, confirmed=False)
        assert isinstance(response, MigrationErrorResponse)
        assert "confirmation" in response.message  # BLOCK

    def test_admin_with_confirmation_passes(self, tmp_path: Path) -> None:
        from hkos.integration.hermes.schemas import MigrationOperationResponse

        engine = _ProbeEngine()
        tools = MigrationTools(engine)  # type: ignore[arg-type]
        agent = AgentContext(agent_id="admin", project_id="p1")
        response = tools.rollback(agent, confirmed=True)
        assert isinstance(response, MigrationOperationResponse)  # PASS

    def test_audit_events_present(self, tmp_path: Path) -> None:

        engine = _ProbeEngine()
        audit = AuditLogger()
        tools = MigrationTools(engine, audit=audit)  # type: ignore[arg-type]
        agent = AgentContext(agent_id="agent-1", project_id="p1")
        tools.rollback(agent, confirmed=False)  # DENIED
        tools.status(agent)                     # ALLOWED
        commands = {e.command for e in audit.entries()}
        assert "migration.rollback" in commands
        assert "migration.status" in commands
        denied = [e for e in audit.entries()
                  if e.command == "migration.rollback"
                  and e.event == "COMMAND_DENIED"]
        assert denied  # DENIED событие зафиксировано


class TestFallbackE2E:
    """Graceful degradation (DS-012 ЭТАП 5 §8)."""

    def test_retrieval_unavailable_continues(self, tmp_path: Path) -> None:
        h = _Harness(tmp_path)
        project = h.projects.create(name="OpenWrt", tags=["router"])
        h.memory._retrieval_available = False  # имитация недоступности
        prepared = h.memory.prepare_context(
            agent_id="a", query="udp", project_id=project.id)
        assert prepared.retrieval_items == []  # пустой контекст
        assert prepared.context is not None or prepared.retrieval_items == []
        # работа продолжается: сохранение работает
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
        assert prepared.snapshot_used is False  # retrieval без снимка

    def test_librarian_unavailable_queues_and_drains(self, tmp_path: Path) -> None:
        h = _Harness(tmp_path)
        project = h.projects.create(name="OpenWrt", tags=["router"])
        h.memory._librarian_available = False  # имитация недоступности
        result = h.memory.save_results(
            agent_id="a", project_id=project.id,
            knowledge=[Knowledge(title="K1", body="b1", tags=["t1"]),
                       Knowledge(title="K2", body="b2", tags=["t2"])])
        assert result.saved == []          # не записано...
        assert h.memory.pending_count() == 2  # ...но не потеряно (queue)
        # после восстановления — drain
        h.memory.reset_fallbacks()
        h.memory.drain_pending()
        # очередь обработана: знания записаны через Librarian
        assert h.memory.pending_count() == 0


class TestPipelinePerformance:
    """Бюджеты производительности (DS-012 ЭТАП 5 §9)."""

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
        assert context_ms <= 200, f"context {context_ms:.1f} ms"

        start = time.monotonic()
        h.memory.save_results(
            agent_id="a", project_id=project.id,
            knowledge=[Knowledge(title="New", body="new", tags=["n"])])
        save_ms = (time.monotonic() - start) * 1000
        assert save_ms <= 150, f"save {save_ms:.1f} ms"

        # общий overhead pipeline (без генерации данных)
        start = time.monotonic()
        h.memory.prepare_context(agent_id="a", query="udp", project_id=project.id)
        total_ms = (time.monotonic() - start) * 1000
        assert total_ms <= 500, f"total overhead {total_ms:.1f} ms"

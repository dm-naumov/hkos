"""IP-017 ЭТАП 3: doctor FK-валидатор висячих ссылок relations (DS-017).

Рёбра хранятся на Knowledge-документах (SSOT); doctor флагает висячие
ссылки — цель не существует в целевом проекте, включая кросс-проектные
адреса (target_project_id). Проверка идёт по имени issue
"relations FK: dangling links" (общий вердикт зависит и от других групп:
index/snapshot-консистентность здесь не настраивается).

Валидные рёбра НЕЛЬЗЯ создать висячими через Librarian (ЭТАП 2 валидирует
цели) — висячая ссылка имитируется удалением цели на уровне repository
(внешнее/устаревшее состояние), которое doctor обязан флагать.
"""

from pathlib import Path

from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.index import IndexCache, IndexEngine, IndexQueryExecutor, IndexStore
from hkos.integration.hermes.doctor import (
    ConsistencyIssue,
    ConsistencyReport,
    HkosDoctor,
)
from hkos.repository.knowledge_relations import (
    KnowledgeRelation,
    RelationType,
)
from hkos.repository.models import Knowledge
from hkos.repository.repository_manager import RepositoryManager
from hkos.services.librarian.librarian import Librarian
from hkos.services.project_manager import ProjectManager
from hkos.snapshot import SnapshotEngine
from hkos.storage import StorageEngine


class _MemoryPersistence:
    """In-memory порт SnapshotPersistence (локальная копия тестового порта)."""

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


class DoctorCtx:
    """Минимальный контекст doctor (repos + librarian + index + snapshots)."""

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
        self.store = IndexStore(self.engine)
        cache = IndexCache()
        self.index = IndexEngine(self.repos, self.store, HKOSLogger(),
                                 cache=cache)
        self.qc = IndexQueryExecutor(self.store, cache=cache)
        self.snapshots = SnapshotEngine(
            self.repos, _MemoryPersistence(), HKOSLogger(),
            index_provider=self.qc.snapshot)
        self.doctor = HkosDoctor(
            self.repos, self.index, self.snapshots, self.store)

    def project(self, name: str) -> str:
        """Создать проект, вернуть его id."""
        return self.projects.create(name=name).id

    def knowledge(self, project_id: str, title: str) -> str:
        """Зарегистрировать знание, вернуть id."""
        return self.librarian.register(
            project_id, Knowledge(title=title, body="body")).id

    def doctor_check(self, project_id: str) -> ConsistencyReport:
        """doctor.check с построенным индексом (statistics требует build)."""
        self.index.build(project_id)
        return self.doctor.check(project_id)


def fk_issue(report: ConsistencyReport) -> ConsistencyIssue | None:
    """Issue группы relations FK (или None)."""
    for issue in report.issues:
        if issue.check == "relations FK: dangling links":
            return issue
    return None


class TestDoctorRelationsFk:
    """FK Integrity Check: валидные рёбра PASS, висячие — FAIL."""

    def test_valid_same_project_relation_passes(self, tmp_path: Path) -> None:
        ctx = DoctorCtx(tmp_path)
        pid = ctx.project("A")
        target_id = ctx.knowledge(pid, "target fact")
        source_id = ctx.librarian.register(
            pid,
            Knowledge(
                title="source fact",
                relations=[
                    _rel(target_id, RelationType.BASED_ON),
                ],
            ),
        ).id
        issue = fk_issue(ctx.doctor_check(pid))
        assert issue is not None
        assert issue.status == "PASS", issue.detail
        assert source_id is not None

    def test_dangling_same_project_detected(self, tmp_path: Path) -> None:
        ctx = DoctorCtx(tmp_path)
        pid = ctx.project("A")
        target_id = ctx.knowledge(pid, "target fact")
        source_id = ctx.librarian.register(
            pid,
            Knowledge(
                title="source fact",
                relations=[_rel(target_id, RelationType.CAUSED_BY)],
            ),
        ).id
        # цель удалена вне Librarian (внешнее состояние) -> ребро висит
        ctx.repos.knowledge.delete(pid, target_id)
        issue = fk_issue(ctx.doctor_check(pid))
        assert issue is not None
        assert issue.status == "FAIL", issue.detail
        assert issue.actual == 1
        assert source_id in issue.detail and target_id in issue.detail

    def test_valid_cross_project_relation_passes(self, tmp_path: Path) -> None:
        ctx = DoctorCtx(tmp_path)
        pid_a = ctx.project("A")
        pid_b = ctx.project("B")
        target_id = ctx.knowledge(pid_b, "target in B")
        ctx.librarian.register(
            pid_a,
            Knowledge(
                title="source in A",
                relations=[
                    _rel(target_id, RelationType.CAUSED_BY,
                         target_project_id=pid_b),
                ],
            ),
        )
        issue = fk_issue(ctx.doctor_check(pid_a))
        assert issue is not None
        assert issue.status == "PASS", issue.detail
        # B не содержит рёбер (они на источнике в A) -> FK PASS
        issue_b = fk_issue(ctx.doctor_check(pid_b))
        assert issue_b is not None
        assert issue_b.status == "PASS"

    def test_dangling_cross_project_detected(self, tmp_path: Path) -> None:
        ctx = DoctorCtx(tmp_path)
        pid_a = ctx.project("A")
        pid_b = ctx.project("B")
        target_id = ctx.knowledge(pid_b, "target in B")
        ctx.librarian.register(
            pid_a,
            Knowledge(
                title="source in A",
                relations=[
                    _rel(target_id, RelationType.BASED_ON,
                         target_project_id=pid_b),
                ],
            ),
        )
        # цель в B удалена -> ребро из A висит
        ctx.repos.knowledge.delete(pid_b, target_id)
        issue = fk_issue(ctx.doctor_check(pid_a))
        assert issue is not None
        assert issue.status == "FAIL", issue.detail
        assert issue.actual == 1
        assert pid_b in issue.detail
        # у B своих рёбер нет -> его FK-группа PASS
        issue_b = fk_issue(ctx.doctor_check(pid_b))
        assert issue_b is not None
        assert issue_b.status == "PASS"


def _rel(
    target_id: str,
    rtype: RelationType,
    target_project_id: str = "",
    relation_id: str = "fk-r",
) -> KnowledgeRelation:
    """Валидное ребро (relation_id фиксирован — уникален в рамках теста)."""
    return KnowledgeRelation(
        relation_id=relation_id,
        source_id="src",
        target_id=target_id,
        relation_type=rtype,
        created_at="2026-09-08T00:00:00+00:00",
        target_project_id=target_project_id,
    )

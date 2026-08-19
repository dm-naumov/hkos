"""DS-015 ЭТАП 3: Failure Readiness (эксплуатационные аварии).
================================================================
A) Index corruption  B) Snapshot corruption  C) Cache corruption
D) Unexpected shutdown (process killed -> restart).
"""

import subprocess
import sys
from pathlib import Path

import pytest

from hkos.core.logger import HKOSLogger
from hkos.repository.models import Knowledge
from hkos.snapshot import SnapshotEngine
from tests.system.assertions import assert_retrievable
from tests.system.ds015.fixtures import create_ds015_context
from tests.system.fixtures import _MemoryPersistence

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PKG_PARENT = str(_REPO_ROOT.parent)

_KILL_SCRIPT = "\n".join([
    "import sys",
    f"sys.path.insert(0, {_PKG_PARENT!r})",
    "from pathlib import Path",
    "from hkos.core.config import ConfigLoader",
    "from hkos.core.logger import HKOSLogger",
    "from hkos.core.version import VersionManager",
    "from hkos.storage import StorageEngine",
    "from hkos.repository.repository_manager import RepositoryManager",
    "from hkos.services.librarian import Librarian",
    "from hkos.repository.models import Knowledge, Project",
    "root = Path(sys.argv[1])",
    "cfg = ConfigLoader(profile='production')",
    "cfg.load()",
    "engine = StorageEngine(root=str(root), config=cfg,",
    "                       logger=HKOSLogger(), version=VersionManager())",
    "engine.initialize()",
    "repos = RepositoryManager(engine)",
    "lib = Librarian(repos, HKOSLogger())",
    "p = repos.projects.save(Project(name='KillMe', tags=['kill']))",
    "for i in range(10):",
    "    lib.register(p.id, Knowledge(",
    "        title=f'KF{i}fact udp', body='udp', tags=['udp']))",
    "import os",
    "os._exit(1)  # имитация kill -9",
])


class TestFailureReadiness:
    """Аварии: обнаружение, изоляция SSOT, восстановление."""

    def test_scenario_a_index_corruption(self, tmp_path: Path) -> None:
        ctx = create_ds015_context(tmp_path)
        project = ctx.project.create(name="A", tags=["fr"])
        ctx.librarian.register(project.id, Knowledge(
            title="AFact udp", body="udp", tags=["udp"]))
        ctx.index.build(project.id)
        index_file = (tmp_path / "projects" / project.id / "indexes" / "entities.idx")
        index_file.write_text("{ broken")
        from hkos.storage.exceptions import StorageSerializationError
        with pytest.raises(StorageSerializationError):
            ctx.retrieval.retrieve("AFact", project_id=project.id)
        assert ctx.repos.knowledge.count(project.id) == 1  # Repository цел
        ctx.index.rebuild(project.id)
        assert_retrievable(ctx, project.id, "AFact", "AFact")

    def test_scenario_b_snapshot_corruption(self, tmp_path: Path) -> None:
        ctx = create_ds015_context(tmp_path)
        snapshots = SnapshotEngine(ctx.repos, _MemoryPersistence(), HKOSLogger(),
                                   index_provider=ctx.qc.snapshot)
        project = ctx.project.create(name="B", tags=["fr"])
        ctx.librarian.register(project.id, Knowledge(
            title="BFact udp", body="udp", tags=["udp"]))
        ctx.index.build(project.id)
        snapshots.create(project.id, reason="valid")
        from hkos.kernel.snapshot_document import SnapshotDocument
        snapshots._persistence.save(project.id, SnapshotDocument(
            snapshot_id="snapshot-00001", project_id=project.id,
            statistics={"knowledge": 999}).as_dict())
        corrupted = snapshots.load(project.id)
        assert int(corrupted.statistics.get("knowledge", 0)) == 999  # invalid
        assert ctx.repos.knowledge.count(project.id) == 1  # Repository не изменён
        snapshots.create(project.id, reason="recovered", force=True)
        assert int(snapshots.load(project.id).statistics.get("knowledge", 0)) == 1

    def test_scenario_c_cache_corruption(self, tmp_path: Path) -> None:
        """Cache corruption: инвалидация; данные из SSOT; Knowledge цел."""
        from hkos.performance.integration import PerformanceIntegration

        ctx = create_ds015_context(tmp_path)
        project = ctx.project.create(name="C", tags=["fr"])
        for i in range(20):
            ctx.librarian.register(project.id, Knowledge(
                title=f"CFact{i} udp", body="udp", tags=["udp"]))
        ctx.index.build(project.id)
        perf = PerformanceIntegration()
        measured = perf.wrap_retrieval(ctx.retrieval,
                                       fingerprint=ctx.store.fingerprint)
        measured.retrieve("udp", project_id=project.id)
        # ПОВРЕЖДЕНИЕ кэша (подмена записи)
        perf.cache.clear()
        perf.cache.set("retrieval:p1::udp:", "CORRUPTED")
        # инвалидация/перестройка: данные из SSOT (Repository+Index)
        again = measured.retrieve("udp", project_id=project.id)
        assert again != "CORRUPTED"
        assert len(again.items) >= 1
        # Knowledge не повреждён
        assert ctx.repos.knowledge.count(project.id) == 20

    def test_scenario_d_unexpected_shutdown(self, tmp_path: Path) -> None:
        """Process killed -> restart: нет частичных записей, нет потери."""
        subprocess.run([sys.executable, "-c", _KILL_SCRIPT, str(tmp_path)],
                       cwd=str(_REPO_ROOT), check=False)
        # RESTART: повторная инициализация
        ctx = create_ds015_context(tmp_path)
        project = next(p for p in ctx.project.list() if p.name == "KillMe")
        # нет частичных записей: ровно 10
        assert ctx.repos.knowledge.count(project.id) == 10
        # нет .tmp-артефактов
        leftovers = list((tmp_path / "projects").rglob("*.tmp*"))
        assert leftovers == [], f"leftover tmp files: {leftovers}"
        # нет потери памяти: индекс строится (auto_index) -> retrieval
        ctx.index.build(project.id)
        result = ctx.retrieval.retrieve("KF5fact", project_id=project.id)
        assert any("KF5fact" in str(i.entity.title) for i in result.items)

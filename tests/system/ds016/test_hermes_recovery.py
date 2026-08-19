"""DS-016 ЭТАП 3.5: Hermes Failure Recovery.
================================================================
A) IndexCache broken -> ошибка обнаружена; SSOT цел; rebuild.
B) Snapshot broken -> Repository не изменён.
C) Unexpected shutdown: child сохраняет знания -> os._exit(1) -> restart
   без частичных записей/tmp; память доступна.
"""

import subprocess
import sys
from pathlib import Path

from hkos.repository.models import Knowledge
from tests.system.ds016.hermes_context import create_hermes_context

_KILL_SCRIPT = "\n".join([
    "import sys",
    "sys.path.insert(0, '/home/dm'); sys.path.insert(0, '/home/dm/hkos')",
    "from pathlib import Path",
    "from tests.system.ds016.hermes_context import create_hermes_context",
    "from hkos.repository.models import Knowledge",
    "root = Path(sys.argv[1])",
    "ctx = create_hermes_context(root)",
    "p = ctx.project.create(name='KillHermes', tags=['hermes'])",
    "for i in range(10):",
    "    ctx.save_after_task(p.id, Knowledge(",
    "        title=f'HK{i}fact udp', body='udp', tags=['udp']))",
    "import os",
    "os._exit(1)  # имитация kill -9",
])


class TestHermesRecovery:
    """Восстановление после сбоев Hermes-контура."""

    def test_a_indexcache_broken(self, tmp_path: Path) -> None:
        ctx = create_hermes_context(tmp_path)
        project = ctx.project.create(name="CacheBrk", tags=["hermes"])
        ctx.save_after_task(project.id, Knowledge(
            title="CacheFact udp", body="udp", tags=["udp"]))
        # повреждение файла индекса
        index_file = (tmp_path / "projects" / project.id / "indexes" / "entities.idx")
        index_file.write_text("{ broken")
        from hkos.storage.exceptions import StorageSerializationError
        # 1) ошибка обнаруживается на уровне RetrievalEngine (не скрыта)
        try:
            ctx.retrieval.retrieve("udp", project_id=project.id)
            detected = False
        except StorageSerializationError:
            detected = True
        assert detected
        # 2) хук (MemoryService fallback, дизайн DS-012): НЕ выдаёт
        #    ложный контекст (пустой результат, не фейковые данные)
        bundle = ctx.retrieve_before_task("udp", project_id=project.id)
        assert bundle["retrieval_items"] == []
        # SSOT цел
        assert ctx.repos.knowledge.count(project.id) == 1
        # rebuild восстанавливает (и хук снова работает)
        ctx.index.rebuild(project.id)
        bundle = ctx.retrieve_before_task("udp", project_id=project.id)
        assert len(bundle["retrieval_items"]) >= 1

    def test_b_snapshot_broken(self, tmp_path: Path) -> None:
        ctx = create_hermes_context(tmp_path)
        project = ctx.project.create(name="SnapBrk", tags=["hermes"])
        ctx.save_after_task(project.id, Knowledge(
            title="SnapFact udp", body="udp", tags=["udp"]))
        ctx.snapshots.create(project.id, reason="valid")
        from hkos.kernel.snapshot_document import SnapshotDocument
        ctx.snapshots._persistence.save(project.id, SnapshotDocument(
            snapshot_id="snapshot-00001", project_id=project.id,
            statistics={"knowledge": 999}).as_dict())
        assert int(ctx.snapshots.load(project.id).statistics.get("knowledge", 0)) == 999
        # Repository не изменён
        assert ctx.repos.knowledge.count(project.id) == 1
        ctx.snapshots.create(project.id, reason="recovered", force=True)
        assert int(ctx.snapshots.load(project.id).statistics.get("knowledge", 0)) == 1

    def test_c_unexpected_shutdown(self, tmp_path: Path) -> None:
        subprocess.run([sys.executable, "-c", _KILL_SCRIPT, str(tmp_path)],
                       cwd="/home/dm/hkos", check=False)
        # RESTART
        ctx = create_hermes_context(tmp_path)
        project = next(p for p in ctx.project.list() if p.name == "KillHermes")
        assert ctx.repos.knowledge.count(project.id) == 10  # нет частичных
        leftovers = list((tmp_path / "projects").rglob("*.tmp*"))
        assert leftovers == [], f"tmp files: {leftovers}"
        ctx.index.rebuild(project.id)
        bundle = ctx.retrieve_before_task("HK5fact", project_id=project.id)
        assert len(bundle["retrieval_items"]) >= 1  # память доступна

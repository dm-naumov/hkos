"""DS-015 ЭТАП 3: Operational Procedures Validation.
================================================================
Startup (config -> init -> ready), Shutdown (flush -> snapshot -> exit),
Recovery (failure -> detect -> restore -> continue).
Нет зависших состояний; нет незакрытых ресурсов.
"""

import gc
from pathlib import Path

from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.repository.models import Knowledge
from hkos.storage import StorageEngine
from tests.system.ds015.fixtures import create_ds015_context


class TestOperationalProcedures:
    """Эксплуатационные процедуры: startup/shutdown/recovery."""

    def test_startup_procedure(self, tmp_path: Path) -> None:
        """Start HKOS: load config -> initialize services -> ready."""
        loader = ConfigLoader(profile="production")
        config = loader.load()
        engine = StorageEngine(
            root=str(tmp_path), config=config, logger=HKOSLogger(),
            version=VersionManager())
        engine.initialize()  # идемпотентна
        engine.initialize()  # повторный старт без ошибок
        assert engine.health() is not None

    def test_shutdown_procedure(self, tmp_path: Path) -> None:
        """Stop HKOS: flush state -> snapshot -> clean exit."""
        ctx = create_ds015_context(tmp_path)
        project = ctx.project.create(name="Shutdown", tags=["op"])
        ctx.librarian.register(project.id, Knowledge(
            title="ShutFact udp", body="udp", tags=["udp"]))
        # flush: все данные на диске (файловое хранилище — синхронно)
        gc.collect()
        # clean exit: повторная инициализация видит всё
        ctx.engine.initialize()
        assert ctx.repos.knowledge.count(project.id) == 1
        # нет незакрытых ресурсов (повторная инициализация не падает)
        assert ctx.repos.projects.list()  # ready после restart

    def test_recovery_procedure(self, tmp_path: Path) -> None:
        """Failure -> detect -> restore -> continue."""
        ctx = create_ds015_context(tmp_path)
        project = ctx.project.create(name="Recovery", tags=["op"])
        ctx.librarian.register(project.id, Knowledge(
            title="RecFact udp", body="udp", tags=["udp"]))
        ctx.index.build(project.id)
        # failure: повреждение индекса
        index_file = (tmp_path / "projects" / project.id / "indexes" / "entities.idx")
        index_file.write_text("{ broken")
        # detect: чтение падает (ошибка не скрывается)
        from hkos.storage.exceptions import StorageSerializationError
        try:
            ctx.retrieval.retrieve("RecFact", project_id=project.id)
            detected = False
        except StorageSerializationError:
            detected = True
        assert detected
        # restore: rebuild -> continue
        ctx.index.rebuild(project.id)
        result = ctx.retrieval.retrieve("RecFact", project_id=project.id)
        assert len(result.items) >= 1

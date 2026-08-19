"""DS-016 ЭТАП 2: Startup Hook (A).
================================================================
Hermes startup -> production config -> initialize (идемпотентно) ->
Repository ready -> Index ready -> Snapshot validated -> READY.
Ошибка инициализации -> исключение (НЕ ложный READY).
"""

from pathlib import Path

from tests.system.ds016.hermes_context import create_hermes_context


class TestStartupIntegration:
    """Production startup lifecycle."""

    def test_production_config_and_initialize(self, tmp_path: Path) -> None:
        ctx = create_hermes_context(tmp_path)
        assert ctx.config.get("hkos.version") == "1.0.0"
        assert ctx.engine.health() is not None

    def test_repeat_initialize_idempotent(self, tmp_path: Path) -> None:
        ctx = create_hermes_context(tmp_path)
        project = ctx.project.create(name="Persist", tags=["startup"])
        ctx.librarian.register(project.id, __import__(
            "hkos.repository.models", fromlist=["Knowledge"]).Knowledge(
                title="PersistFact udp", body="udp", tags=["udp"]))
        ctx.engine.initialize()   # повторный запуск
        ctx.engine.initialize()   # ещё раз
        assert ctx.repos.knowledge.count(project.id) == 1  # память цела

    def test_ready_state(self, tmp_path: Path) -> None:
        ctx = create_hermes_context(tmp_path)
        status = ctx.hooks.startup()
        assert status["ready"] is True
        assert status["repository_available"] is True
        assert status["index_available"] is True

    def test_repository_index_snapshot_available(self, tmp_path: Path) -> None:
        ctx = create_hermes_context(tmp_path)
        project = ctx.project.create(name="Avail", tags=["startup"])
        knowledge = ctx.librarian.register(project.id, __import__(
            "hkos.repository.models", fromlist=["Knowledge"]).Knowledge(
                title="AvailFact udp", body="udp", tags=["udp"]))
        ctx.index.build(project.id)
        ctx.snapshots.create(project.id, reason="startup")
        assert ctx.repos.knowledge.exists(project.id, knowledge.id)
        assert int(ctx.index.statistics(project.id).get("knowledge", 0)) == 1
        assert ctx.snapshots.load(project.id) is not None

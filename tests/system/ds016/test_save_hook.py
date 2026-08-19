"""DS-016 ЭТАП 2: Save-After-Task Hook (D/E/F).
================================================================
Task result -> Librarian (не напрямую) -> canonicalize -> Index ->
Snapshot. DECISION/FAILURE/CONFIGURATION; FAILURE с cause/recommendations.
AgentLock WRITE: 2 concurrent writers x 20 = 40, без потерь/дубликатов.
"""

import threading
from pathlib import Path

from hkos.repository.models import Knowledge
from tests.system.ds016.hermes_context import create_hermes_context


class TestSaveHook:
    """Save после задачи: полный путь записи (SSOT)."""

    def test_save_through_librarian(self, tmp_path: Path) -> None:
        ctx = create_hermes_context(tmp_path)
        project = ctx.project.create(name="Save", tags=["hermes"])
        knowledge = Knowledge(title="SaveFact udp", body="udp", tags=["udp"])
        result = ctx.save_after_task(project.id, knowledge)
        assert result["saved"], "knowledge not saved"
        # знание retrievable (canonicalize в save-пути)
        ctx.index.build(project.id)
        bundle = ctx.retrieve_before_task("SaveFact", project_id=project.id)
        titles = [str(i.entity.title) for i in bundle["retrieval_items"]]
        assert any("SaveFact" in t for t in titles)

    def test_save_decision_failure_configuration(self, tmp_path: Path) -> None:
        ctx = create_hermes_context(tmp_path)
        project = ctx.project.create(name="DFC", tags=["hermes"])
        decision = Knowledge(title="DecisionSave udp", body="use VLESS",
                             tags=["vless", "udp"], category="DECISION")
        failure = Knowledge(title="FailureSave udp",
                            body="cause: wrong rule\n"
                                 "recommendations: policy routing",
                            tags=["routing", "udp"], kind="negative")
        configuration = Knowledge(title="ConfigSave udp", body="AX3000T",
                                  tags=["router", "udp"],
                                  category="CONFIGURATION")
        ctx.save_after_task(project.id, decision)
        ctx.save_after_task(project.id, failure)
        ctx.save_after_task(project.id, configuration)
        assert ctx.repos.knowledge.count(project.id) == 3
        # FAILURE: cause/recommendations сохранены
        failures = [k for k in ctx.repos.knowledge.list(project.id)
                    if "FailureSave" in k.title]
        assert failures
        assert "cause:" in failures[0].body
        assert "recommendations:" in failures[0].body

    def test_index_and_snapshot_updated(self, tmp_path: Path) -> None:
        ctx = create_hermes_context(tmp_path)
        project = ctx.project.create(name="IdxSnap", tags=["hermes"])
        ctx.save_after_task(project.id, Knowledge(
            title="IdxSnapFact udp", body="udp", tags=["udp"]))
        # index обновлён (save-путь делает index.update)
        assert int(ctx.index.statistics(project.id).get("knowledge", 0)) == 1
        # snapshot обновлён (save-путь делает snapshot create force)
        snapshot = ctx.snapshots.load(project.id)
        assert snapshot is not None
        assert int(snapshot.statistics.get("knowledge", 0)) == 1

    def test_two_concurrent_writers_no_loss(self, tmp_path: Path) -> None:
        """AgentLock WRITE: 2 писателя x 20 = 40; нет потерь/дубликатов."""
        ctx = create_hermes_context(tmp_path)
        project = ctx.project.create(name="Concurrent", tags=["hermes"])
        errors: list[Exception] = []
        saved_count = 0

        def writer(name: str, start: int) -> None:
            nonlocal saved_count
            try:
                for i in range(20):
                    result = ctx.save_after_task(project.id, Knowledge(
                        title=f"{name}K{start + i}fact udp", body="udp",
                        tags=["udp"]))
                    if result["saved"]:
                        saved_count += 1
            except Exception as exc:  # pragma: no cover
                errors.append(exc)

        threads = [
            threading.Thread(target=writer, args=("W1", 0)),
            threading.Thread(target=writer, args=("W2", 100)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        assert saved_count == 40
        assert ctx.repos.knowledge.count(project.id) == 40  # Repository == 40
        # нет дубликатов
        ids = [k.id for k in ctx.repos.knowledge.list(project.id)]
        assert len(ids) == len(set(ids))
        # целостность
        ctx.index.rebuild(project.id)
        assert int(ctx.index.statistics(project.id).get("knowledge", 0)) == 40

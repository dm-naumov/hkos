"""IP-017 ЭТАП 2: валидация relations в write-path Librarian (DS-017 §4.2.1).

Правила: цель существует (включая кросс-проектный lookup), тип допустим,
не self-loop. register/update строго отклоняют невалидные рёбра;
validate_relations даёт мягкий путь (valid, warnings) для MCP/API.
"""

from pathlib import Path

import pytest

from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.repository.knowledge_relations import (
    KnowledgeRelation,
    RelationType,
)
from hkos.repository.models import Knowledge
from hkos.repository.repository_manager import RepositoryManager
from hkos.services.librarian.exceptions import LibrarianError
from hkos.services.librarian.librarian import Librarian
from hkos.services.project_manager import ProjectManager
from hkos.storage import StorageEngine


class TestLibrarianRelationValidation:
    """Валидация relations при авторинге (write-path)."""

    def _ctx(
        self, tmp_path: Path
    ) -> tuple[RepositoryManager, Librarian, ProjectManager]:
        cfg = ConfigLoader(profile="development")
        cfg.load()
        engine = StorageEngine(
            root=str(tmp_path), config=cfg, logger=HKOSLogger(),
            version=VersionManager(),
        )
        engine.initialize()
        repos = RepositoryManager(engine)
        return repos, Librarian(repos, HKOSLogger()), ProjectManager(
            repos, HKOSLogger()
        )

    @staticmethod
    def _rel(
        target_id: str,
        rtype: RelationType = RelationType.REFERENCE_TO,
        target_project_id: str = "",
        relation_id: str = "r-1",
    ) -> KnowledgeRelation:
        return KnowledgeRelation(
            relation_id=relation_id,
            source_id="src",
            target_id=target_id,
            relation_type=rtype,
            created_at="2026-09-08T00:00:00+00:00",
            target_project_id=target_project_id,
        )

    def test_valid_relation_is_persisted(self, tmp_path: Path) -> None:
        repos, lib, pm = self._ctx(tmp_path)
        project = pm.create(name="P1", tags=["t"])
        pid = project.id
        target = lib.register(pid, Knowledge(title="target fact", body="x"))
        saved = lib.register(
            pid,
            Knowledge(
                title="source fact",
                body="y",
                relations=[self._rel(target.id, RelationType.BASED_ON)],
            ),
        )
        loaded = repos.knowledge.load(pid, saved.id)
        assert len(loaded.relations) == 1
        rel = loaded.relations[0]
        assert rel.target_id == target.id
        assert rel.relation_type is RelationType.BASED_ON
        assert rel.target_project_id == ""

    def test_unknown_target_raises(self, tmp_path: Path) -> None:
        _, lib, pm = self._ctx(tmp_path)
        pid = pm.create(name="P1", tags=["t"]).id
        with pytest.raises(LibrarianError, match="target not found"):
            lib.register(
                pid,
                Knowledge(
                    title="dangling",
                    relations=[self._rel("00000000-0000-0000-0000-000000000000")],
                ),
            )

    def test_self_loop_raises(self, tmp_path: Path) -> None:
        _, lib, pm = self._ctx(tmp_path)
        pid = pm.create(name="P1", tags=["t"]).id
        knowledge = Knowledge(
            title="self-ref",
            relations=[self._rel("self-1", RelationType.REFERENCE_TO)],
        )
        knowledge.id = "self-1"
        with pytest.raises(LibrarianError, match="self-loop"):
            lib.register(pid, knowledge)

    def test_cross_project_valid_relation(self, tmp_path: Path) -> None:
        repos, lib, pm = self._ctx(tmp_path)
        pid_a = pm.create(name="A", tags=["t"]).id
        pid_b = pm.create(name="B", tags=["t"]).id
        target = lib.register(pid_b, Knowledge(title="target in B", body="x"))
        saved = lib.register(
            pid_a,
            Knowledge(
                title="source in A",
                body="y",
                relations=[self._rel(
                    target.id, RelationType.CAUSED_BY,
                    target_project_id=pid_b, relation_id="xp-1",
                )],
            ),
        )
        loaded = repos.knowledge.load(pid_a, saved.id)
        rel = loaded.relations[0]
        assert rel.target_project_id == pid_b
        assert rel.target_id == target.id

    def test_cross_project_unknown_project_raises(self, tmp_path: Path) -> None:
        _, lib, pm = self._ctx(tmp_path)
        pid = pm.create(name="A", tags=["t"]).id
        with pytest.raises(LibrarianError, match="target project not found"):
            lib.register(
                pid,
                Knowledge(
                    title="bad cross",
                    relations=[self._rel(
                        "any-id", RelationType.BASED_ON,
                        target_project_id="no-such-project",
                    )],
                ),
            )

    def test_cross_project_unknown_target_raises(self, tmp_path: Path) -> None:
        _, lib, pm = self._ctx(tmp_path)
        pid_a = pm.create(name="A", tags=["t"]).id
        pid_b = pm.create(name="B", tags=["t"]).id
        with pytest.raises(LibrarianError, match="target not found"):
            lib.register(
                pid_a,
                Knowledge(
                    title="dangling cross",
                    relations=[self._rel(
                        "00000000-0000-0000-0000-000000000000",
                        RelationType.CAUSED_BY, target_project_id=pid_b,
                    )],
                ),
            )

    def test_validate_relations_soft_path(self, tmp_path: Path) -> None:
        _, lib, pm = self._ctx(tmp_path)
        pid = pm.create(name="P1", tags=["t"]).id
        target = lib.register(pid, Knowledge(title="target", body="x"))
        valid, warnings = lib.validate_relations(
            pid,
            "src",
            [
                self._rel(target.id, RelationType.BASED_ON, relation_id="ok-1"),
                self._rel("00000000-0000-0000-0000-000000000000",
                          relation_id="bad-1"),
            ],
        )
        assert len(valid) == 1 and valid[0].target_id == target.id
        assert len(warnings) == 1 and "target not found" in warnings[0]

    def test_update_with_new_invalid_relation_raises(
        self, tmp_path: Path
    ) -> None:
        repos, lib, pm = self._ctx(tmp_path)
        pid = pm.create(name="P1", tags=["t"]).id
        saved = lib.register(pid, Knowledge(title="doc", body="v1"))
        # Правка тела без изменения relations (пустых) — проходит
        updated = repos.knowledge.load(pid, saved.id)
        updated.body = "v2"
        lib.update(pid, updated)
        # Новое невалидное ребро — строгий отказ
        updated = repos.knowledge.load(pid, saved.id)
        updated.relations = [
            self._rel("00000000-0000-0000-0000-000000000000", relation_id="nx"),
        ]
        with pytest.raises(LibrarianError, match="target not found"):
            lib.update(pid, updated)

    def test_update_with_unchanged_valid_relations_passes(
        self, tmp_path: Path
    ) -> None:
        repos, lib, pm = self._ctx(tmp_path)
        pid = pm.create(name="P1", tags=["t"]).id
        target = lib.register(pid, Knowledge(title="target", body="x"))
        saved = lib.register(
            pid,
            Knowledge(
                title="source", body="v1",
                relations=[self._rel(target.id, RelationType.BASED_ON,
                                     relation_id="keep-1")],
            ),
        )
        # Изменение тела при неизменном валидном наборе рёбер — проходит
        updated = repos.knowledge.load(pid, saved.id)
        updated.body = "v2"
        lib.update(pid, updated)
        reloaded = repos.knowledge.load(pid, saved.id)
        assert reloaded.body == "v2"
        assert len(reloaded.relations) == 1

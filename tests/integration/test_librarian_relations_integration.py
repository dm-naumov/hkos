"""Integration test: DS-006A §11 сценарий.

A, B -> Merge -> Relations -> Canonical -> History -> Repository

Проверки: отношения созданы (4 двусторонних), исходные Knowledge
неизменны, parent_ids сохранены, History сохранена.
"""

from pathlib import Path

from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.repository.knowledge_relations import RelationType
from hkos.repository.models import Knowledge
from hkos.repository.repository_manager import RepositoryManager
from hkos.services.librarian.knowledge_status import KNOWLEDGE_STATUS_CANONICAL
from hkos.services.librarian.librarian import Librarian
from hkos.storage import StorageEngine


class TestLibrarianRelationsIntegration:
    """Полный сценарий Merge -> Relations -> Canonical -> History."""

    def _librarian(self, tmp_path: Path) -> tuple[Librarian, StorageEngine]:
        cfg = ConfigLoader(profile="development")
        cfg.load()
        engine = StorageEngine(
            root=str(tmp_path), config=cfg, logger=HKOSLogger(), version=VersionManager()
        )
        engine.initialize()
        return Librarian(RepositoryManager(engine), HKOSLogger()), engine

    def test_merge_relations_canonical_history_repository(self, tmp_path: Path) -> None:
        lib, engine = self._librarian(tmp_path)

        # A и B
        a = lib.register("p1", Knowledge(title="TProxy UDP works", body="from A"))
        b = lib.register("p1", Knowledge(title="tproxy udp works", body="from B"))

        # Merge -> C (CANONICAL) с двусторонними отношениями
        merged = lib.merge("p1", a.id, b.id, reason="same observation")
        assert merged.status == KNOWLEDGE_STATUS_CANONICAL

        # Relations: 4 двусторонние записи
        pairs = {
            (r.source_id, r.target_id, r.relation_type) for r in merged.relations
        }
        assert pairs == {
            (a.id, merged.id, RelationType.MERGED_FROM),
            (b.id, merged.id, RelationType.MERGED_FROM),
            (merged.id, a.id, RelationType.DERIVED_FROM),
            (merged.id, b.id, RelationType.DERIVED_FROM),
        }

        # parent_ids сохранены (обратная совместимость)
        assert merged.parent_ids == [a.id, b.id]

        # Canonical: C создан CANONICAL (merge); канонизация A допустима
        canonical_a = lib.canonicalize("p1", a.id)
        assert canonical_a.status == KNOWLEDGE_STATUS_CANONICAL

        # History сохранена на C (запись Merge от Merger)
        entries = lib.history("p1", merged.id)
        assert [e.event for e in entries] == ["Merged"]
        assert "merge_reason=same observation" in entries[0].details

        # Repository: документы на диске, отношения персистентны
        reloaded = lib._load("p1", merged.id)
        assert len(reloaded.relations) == 4
        assert engine.exists(f"projects/p1/knowledge/{merged.id}.json")

        # Исходные Knowledge неизменны (immutability)
        a_after = lib._load("p1", a.id)
        b_after = lib._load("p1", b.id)
        assert a_after.title == "TProxy UDP works"
        assert b_after.title == "tproxy udp works"
        assert a_after.relations == []
        assert b_after.relations == []
        assert a_after.parent_ids == []

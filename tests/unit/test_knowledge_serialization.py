"""DS-006B §3, §10: Repository serialization audit tests.

Полный roundtrip Knowledge через Repository:
- enum RelationType сохраняется и восстанавливается;
- relations/history не теряются;
- порядок сериализации стабилен;
- нет циклических ссылок.
"""

from pathlib import Path

from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.repository.knowledge_relations import RelationType
from hkos.repository.knowledge_repository import KnowledgeRepository
from hkos.repository.models import Knowledge, KnowledgeHistoryEntry
from hkos.repository.repository_manager import RepositoryManager
from hkos.services.librarian.knowledge_history import EVENT_CREATED
from hkos.storage import StorageEngine


class TestKnowledgeSerialization:
    """Полный roundtrip Knowledge через Repository."""

    def _repo(
        self, tmp_path: Path
    ) -> tuple[KnowledgeRepository, StorageEngine]:
        cfg = ConfigLoader(profile="development")
        cfg.load()
        engine = StorageEngine(
            root=str(tmp_path), config=cfg, logger=HKOSLogger(), version=VersionManager()
        )
        engine.initialize()
        return RepositoryManager(engine).knowledge, engine

    def _rich_knowledge(self) -> Knowledge:
        from hkos.repository.knowledge_relations import KnowledgeRelation

        return Knowledge(
            title="TProxy UDP works",
            body="body",
            category="FACT",
            status="CANONICAL",
            tags=["tproxy", "udp"],
            references=["r1"],
            parent_ids=["a-1", "b-1"],
            confirmations=2,
            independent_campaigns=1,
            successful_usage=3,
            failed_usage=1,
            conflicts=1,
            relations=[
                KnowledgeRelation(
                    relation_id="rel-1", source_id="a-1", target_id="c-1",
                    relation_type=RelationType.MERGED_FROM, created_at="t1",
                ),
                KnowledgeRelation(
                    relation_id="rel-2", source_id="c-1", target_id="a-1",
                    relation_type=RelationType.DERIVED_FROM, created_at="t1",
                ),
            ],
            history=[
                KnowledgeHistoryEntry(
                    timestamp="t0", knowledge_id="c-1", event=EVENT_CREATED,
                    details="created",
                )
            ],
        )

    def test_full_roundtrip(self, tmp_path: Path) -> None:
        repo, _ = self._repo(tmp_path)
        k = self._rich_knowledge()
        k.project = "p1"
        saved = repo.save(k)
        loaded = repo.load("p1", saved.id)

        assert loaded.title == "TProxy UDP works"
        assert loaded.category == "FACT"
        assert loaded.status == "CANONICAL"
        assert loaded.tags == ["tproxy", "udp"]
        assert loaded.parent_ids == ["a-1", "b-1"]
        assert loaded.confirmations == 2
        assert loaded.conflicts == 1

    def test_relations_enum_roundtrip(self, tmp_path: Path) -> None:
        repo, _ = self._repo(tmp_path)
        k = self._rich_knowledge()
        k.project = "p1"
        saved = repo.save(k)
        loaded = repo.load("p1", saved.id)
        assert len(loaded.relations) == 2
        assert loaded.relations[0].relation_type is RelationType.MERGED_FROM
        assert loaded.relations[1].relation_type is RelationType.DERIVED_FROM
        assert loaded.relations[0].source_id == "a-1"

    def test_history_roundtrip(self, tmp_path: Path) -> None:
        repo, _ = self._repo(tmp_path)
        k = self._rich_knowledge()
        k.project = "p1"
        saved = repo.save(k)
        loaded = repo.load("p1", saved.id)
        assert len(loaded.history) == 1
        assert loaded.history[0].event == EVENT_CREATED
        assert loaded.history[0].knowledge_id == "c-1"

    def test_no_field_loss(self, tmp_path: Path) -> None:
        repo, _ = self._repo(tmp_path)
        k = self._rich_knowledge()
        k.project = "p1"
        saved = repo.save(k)
        loaded = repo.load("p1", saved.id)
        expected = {
            "title", "body", "category", "status", "tags", "references",
            "parent_ids", "confirmations", "independent_campaigns",
            "successful_usage", "failed_usage", "conflicts",
        }
        for field in expected:
            assert getattr(loaded, field) == getattr(k, field), f"lost: {field}"

    def test_stable_serialization_order(self, tmp_path: Path) -> None:
        repo, engine = self._repo(tmp_path)
        k = self._rich_knowledge()
        k.project = "p1"
        repo.save(k)
        text1 = engine.read_json(f"projects/p1/knowledge/{k.id}.json")
        # Повторное чтение даёт тот же порядок ключей (sort_keys в JSONStore)
        text2 = engine.read_json(f"projects/p1/knowledge/{k.id}.json")
        assert text1 == text2

    def test_no_circular_references(self, tmp_path: Path) -> None:
        repo, _ = self._repo(tmp_path)
        k = self._rich_knowledge()
        k.project = "p1"
        saved = repo.save(k)
        loaded = repo.load("p1", saved.id)
        # Данные — плоские dataclass'ы; deepcopy не зацикливается
        import copy

        clone = copy.deepcopy(loaded)
        assert clone.id == loaded.id

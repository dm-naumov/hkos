"""Integration tests: Index Engine (DS-007 §19).

Сценарии:
1. Knowledge Created -> Index Updated
2. Knowledge Archived -> Index Updated
3. Mass Import -> Index Rebuild
4. Broken Index -> Validate -> Rebuild

Примечание: автоматическая связка Librarian -> IndexEngine.update()
намеренно НЕ реализована в DS-007 (потребовала бы изменения DS-006,
что запрещено IP-007); тесты вызывают update() вручную после операций.
"""

from pathlib import Path

from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.index import (
    ENTITY_TYPE_KNOWLEDGE,
    IndexEngine,
    IndexStore,
    KeywordIndex,
)
from hkos.repository.models import Knowledge, Project
from hkos.repository.repository_manager import RepositoryManager
from hkos.services.librarian import Librarian
from hkos.services.librarian.knowledge_status import (
    KNOWLEDGE_STATUS_ARCHIVED,
)
from hkos.storage import StorageEngine


class TestIndexIntegration:
    """Полные сценарии индексирования."""

    def _ctx(
        self, tmp_path: Path
    ) -> tuple[StorageEngine, RepositoryManager, Librarian, IndexEngine]:
        cfg = ConfigLoader(profile="development")
        cfg.load()
        engine = StorageEngine(
            root=str(tmp_path), config=cfg, logger=HKOSLogger(), version=VersionManager()
        )
        engine.initialize()
        repos = RepositoryManager(engine)
        lib = Librarian(repos, HKOSLogger())
        index = IndexEngine(repos, IndexStore(engine), HKOSLogger())
        return engine, repos, lib, index

    def test_scenario1_knowledge_created_index_updated(self, tmp_path: Path) -> None:
        _, repos, lib, index = self._ctx(tmp_path)
        p = repos.projects.save(Project(name="OpenWrt", tags=["router"]))
        index.build(p.id)
        k = lib.register(p.id, Knowledge(title="TProxy UDP", body="udp", tags=["tproxy"]))
        index.update(p.id, k.id, ENTITY_TYPE_KNOWLEDGE)
        kw = KeywordIndex(index.store.read(p.id, "keyword"))
        assert kw.search("tproxy")
        assert index.validate(p.id).valid is True

    def test_scenario2_knowledge_archived_index_updated(self, tmp_path: Path) -> None:
        _, repos, lib, index = self._ctx(tmp_path)
        p = repos.projects.save(Project(name="OpenWrt", tags=["router"]))
        k = lib.register(p.id, Knowledge(title="T", tags=["x"]))
        index.build(p.id)
        lib.archive(p.id, k.id)
        assert lib._load(p.id, k.id).status == KNOWLEDGE_STATUS_ARCHIVED
        index.update(p.id, k.id, ENTITY_TYPE_KNOWLEDGE)
        # Статус в Entity Index обновлён
        from hkos.index import EntityIndex

        entities = EntityIndex(index.store.read(p.id, "entities"))
        record = entities.get(k.id)
        assert record is not None
        assert record["status"] == KNOWLEDGE_STATUS_ARCHIVED
        assert index.validate(p.id).valid is True

    def test_scenario3_mass_import_rebuild(self, tmp_path: Path) -> None:
        _, repos, lib, index = self._ctx(tmp_path)
        p = repos.projects.save(Project(name="OpenWrt", tags=["router"]))
        for i in range(20):
            lib.register(p.id, Knowledge(title=f"Knowledge {i}", body=f"body {i}", tags=["bulk"]))
        index.build(p.id)
        stats = index.statistics(p.id)
        assert stats["knowledge"] == 20
        kw = KeywordIndex(index.store.read(p.id, "keyword"))
        assert len(kw.search("knowledge")) == 20
        index.rebuild(p.id)
        assert index.validate(p.id).valid is True

    def test_scenario4_broken_index_validate_rebuild(self, tmp_path: Path) -> None:
        engine, repos, lib, index = self._ctx(tmp_path)
        p = repos.projects.save(Project(name="OpenWrt", tags=["router"]))
        lib.register(p.id, Knowledge(title="T", tags=["x"]))
        index.build(p.id)
        # Портим индекс: добавляем битую ссылку
        kw = KeywordIndex(index.store.read(p.id, "keyword"))
        kw.add("ghost", ENTITY_TYPE_KNOWLEDGE, p.id, "ghostword")
        from hkos.index.index_builder import _index_doc

        index.store.write(p.id, "keyword", _index_doc(kw.data()))
        broken = index.validate(p.id)
        assert broken.valid is False
        # Восстановление
        index.rebuild(p.id)
        assert index.validate(p.id).valid is True
        # k остался в репозитории и переиндексирован
        assert index.health(p.id)["status"] == "PASS"

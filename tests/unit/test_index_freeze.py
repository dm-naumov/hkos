"""Freeze-condition tests (IP-007, Architectural Freeze Review).

Проверяются обязательные условия Freeze перед DS-007:
1. Retriever НЕ зависит от list()-сканирования (query-пути — только индекс);
2. Relationship Read Contract — единая точка чтения отношений;
3. Index Engine не нарушает Dependency Rule;
4. Никакого прямого обращения к Storage (кроме IndexStore);
5. Работа только через RepositoryManager (сущности).
"""

import os
from pathlib import Path
from unittest import mock

from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.index import IndexEngine, IndexStore, KeywordIndex, TagIndex
from hkos.repository.models import Knowledge, Project
from hkos.repository.repository_manager import RepositoryManager
from hkos.services.librarian import Librarian
from hkos.storage import StorageEngine


class TestFreezeConditions:
    """Условия Architectural Freeze Review."""

    def _ctx(self, tmp_path: Path) -> tuple[StorageEngine, RepositoryManager, IndexEngine]:
        cfg = ConfigLoader(profile="development")
        cfg.load()
        engine = StorageEngine(
            root=str(tmp_path), config=cfg, logger=HKOSLogger(), version=VersionManager()
        )
        engine.initialize()
        repos = RepositoryManager(engine)
        index = IndexEngine(repos, IndexStore(engine), HKOSLogger())
        return engine, repos, index

    def test_queries_do_not_use_list_scanning(self, tmp_path: Path) -> None:
        """Condition 1: query-пути читают только файлы индексов."""
        engine, repos, index = self._ctx(tmp_path)
        p = repos.projects.save(Project(name="OpenWrt", tags=["router"]))
        repos.knowledge.save(Knowledge(project=p.id, title="TProxy UDP", tags=["tproxy"]))
        index.build(p.id)

        # Блокируем list-сканирование репозиториев
        for repo in (repos.knowledge, repos.campaigns, repos.decisions, repos.artifacts):
            mock.patch.object(
                repo, "list",
                side_effect=AssertionError("list() forbidden for Retriever"),
            ).start()

        # Query-пути должны работать ТОЛЬКО по индексу
        kw = KeywordIndex(index.store.read(p.id, "keyword"))
        assert kw.search("tproxy")
        tags = TagIndex(index.store.read(p.id, "tags"))
        assert tags.get_by_tag("tproxy")
        assert index.statistics(p.id)["knowledge"] == 1
        assert index.health(p.id)["status"] == "PASS"

    def test_relationship_read_contract(self, tmp_path: Path) -> None:
        """Condition 2: единый READ-контракт отношений."""
        _, repos, index = self._ctx(tmp_path)
        p = repos.projects.save(Project(name="OpenWrt", tags=["router"]))
        lib = Librarian(repos, HKOSLogger())
        a = lib.register(p.id, Knowledge(title="X works", body=""))
        b = lib.register(p.id, Knowledge(title="x works", body=""))
        merged = lib.merge(p.id, a.id, b.id, reason="dup")
        index.build(p.id)
        rels = index.relations_of_knowledge(p.id, merged.id)
        assert len(rels) == 4
        assert len(index.relations_of_project(p.id)) == 4
        from hkos.index import RelationshipReader

        assert isinstance(index, RelationshipReader)

    def test_no_direct_storage_in_index_except_store(self) -> None:
        """Conditions 3-4: только IndexStore имеет storage-доступ."""
        index_dir = os.path.join(os.path.dirname(__file__), "..", "..", "index")
        for name in sorted(os.listdir(index_dir)):
            if not name.endswith(".py") or name == "index_store.py":
                continue
            source = open(os.path.join(index_dir, name), encoding="utf-8").read()
            assert "StorageEngine" not in source, f"{name}: StorageEngine"
            assert "storage_engine" not in source, f"{name}: storage import"

    def test_index_layer_does_not_import_services(self) -> None:
        """Dependency Rule: index не импортирует services (нет цикла)."""
        index_dir = os.path.join(os.path.dirname(__file__), "..", "..", "index")
        for name in sorted(os.listdir(index_dir)):
            if not name.endswith(".py"):
                continue
            source = open(os.path.join(index_dir, name), encoding="utf-8").read()
            for line in source.splitlines():
                if line.startswith(("from ", "import ")):
                    assert "services" not in line, f"{name}: {line.strip()}"

    def test_incremental_update_does_not_rebuild(self, tmp_path: Path) -> None:
        """Incremental update меняет только записи затронутой сущности."""
        _, repos, index = self._ctx(tmp_path)
        p = repos.projects.save(Project(name="OpenWrt", tags=["router"]))
        k1 = repos.knowledge.save(Knowledge(project=p.id, title="Alpha beta", tags=["a"]))
        repos.knowledge.save(Knowledge(project=p.id, title="Gamma delta", tags=["g"]))
        index.build(p.id)
        kw_before = KeywordIndex(index.store.read(p.id, "keyword"))
        assert kw_before.search("alpha")

        k1b = repos.knowledge.load(p.id, k1.id)
        k1b.title = "Alpha omega"
        repos.knowledge.update(k1b)
        index.update(p.id, k1.id, "knowledge")

        kw_after = KeywordIndex(index.store.read(p.id, "keyword"))
        # Слова k2 (gamma, delta) не тронуты
        assert kw_after.search("gamma")
        assert kw_after.search("delta")
        # Старое слово удалено, новое добавлено
        assert kw_after.search("omega")
        assert kw_after.search("beta") == []
        assert index.validate(p.id).valid is True

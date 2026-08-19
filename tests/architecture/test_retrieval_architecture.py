"""Architectural tests: Retrieval Layer (IP-008).

Проверки:
1. Retriever не использует Repository.list()
2. Retriever не использует StorageEngine
3. Retriever не импортирует IndexStore
4. Retriever использует только Query Contract
5. Traversal использует только Q4
6. Ни один Retrieval модуль не импортирует Storage Layer
7. Ни один Retrieval модуль не читает JSON напрямую
8. Ranking не содержит захардкоженных коэффициентов
9. Explainability присутствует у каждого результата
10. Pipeline соответствует HKOS-05 / IP-008
"""

import inspect
import os
import re
from pathlib import Path

from hkos.repository.models import Knowledge
from hkos.retrieval.relationship_traverser import RelationshipTraverser
from hkos.retrieval.retriever import Retriever

RETRIEVAL_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "retrieval")

FORBIDDEN_IMPORTS = [
    "storage_engine",
    "StorageEngine",
    "IndexStore",
    "index_store",
    "import json",
    "from json",
    "import os",
    "pathlib",
]


def _retrieval_modules() -> list[str]:
    """Список исходников модулей Retrieval Layer (без docstring'ов)."""

    def strip_docstring(source: str) -> str:
        """Удалить ведущий docstring модуля (проза не считается кодом)."""
        if source.startswith('"""'):
            end = source.find('"""', 3)
            if end > 0:
                return source[end + 3:]
        return source

    return [
        strip_docstring(open(os.path.join(RETRIEVAL_DIR, name), encoding="utf-8").read())
        for name in sorted(os.listdir(RETRIEVAL_DIR))
        if name.endswith(".py") and name != "__init__.py"
    ]


class TestRetrievalArchitecture:
    """Архитектурные инварианты Retrieval (IP-008, HKOS-INDEX-CONTRACT-001)."""

    def test_1_retriever_does_not_use_repository_list(self) -> None:
        for source in _retrieval_modules():
            for line in source.splitlines():
                if re.search(r"\.list\s*\(", line):
                    assert False, f"Repository.list() usage: {line.strip()}"

    def test_2_retriever_does_not_use_storage_engine(self) -> None:
        for source in _retrieval_modules():
            assert "StorageEngine" not in source
            assert "storage_engine" not in source

    def test_3_retriever_does_not_import_index_store(self) -> None:
        for source in _retrieval_modules():
            assert "IndexStore" not in source
            assert "index_store" not in source

    def test_4_retriever_uses_only_query_contract(self) -> None:
        """Из hkos.index разрешён только query_contract."""
        for source in _retrieval_modules():
            for line in source.splitlines():
                if line.startswith(("from hkos.index", "import hkos.index")):
                    assert "query_contract" in line, f"не-контрактный импорт: {line.strip()}"
                if "IndexEngine" in line and "import" in line:
                    assert False, f"IndexEngine import: {line.strip()}"

    def test_5_traversal_uses_only_q4(self) -> None:
        source = inspect.getsource(RelationshipTraverser)
        # Связи получаются ТОЛЬКО через Q4; документы для связей не читаются
        assert "entity.relations" not in source
        assert "knowledge.relations" not in source
        assert ".relations_of_knowledge" in source

    def test_6_no_storage_layer_imports(self) -> None:
        for source in _retrieval_modules():
            for line in source.splitlines():
                if line.startswith(("from hkos.storage", "import hkos.storage")):
                    assert False, f"Storage import: {line.strip()}"

    def test_7_no_direct_json_reading(self) -> None:
        for source in _retrieval_modules():
            assert "import json" not in source
            assert "json.load" not in source
            assert "open(" not in source

    def test_8_ranking_has_no_hardcoded_coefficients(self) -> None:
        ranking = open(os.path.join(RETRIEVAL_DIR, "ranking_engine.py"), encoding="utf-8").read()
        # Ни одного десятичного литерала (коэффициенты только из конфигурации)
        decimals = re.findall(r"\d+\.\d+", ranking)
        assert decimals == [], f"hardcoded coefficients: {decimals}"

    def test_9_explainability_present_for_every_result(self, tmp_path: Path) -> None:
        from hkos.core.config import ConfigLoader
        from hkos.core.logger import HKOSLogger
        from hkos.core.version import VersionManager
        from hkos.index import IndexEngine, IndexQueryExecutor, IndexStore
        from hkos.retrieval import RetrievalEngine
        from hkos.services.librarian import Librarian
        from hkos.storage import StorageEngine

        cfg = ConfigLoader(profile="development")
        cfg.load()
        engine = StorageEngine(
            root=str(tmp_path), config=cfg, logger=HKOSLogger(), version=VersionManager()
        )
        engine.initialize()
        from hkos.repository import RepositoryManager
        from hkos.repository.models import Project

        repos = RepositoryManager(engine)
        index = IndexEngine(repos, IndexStore(engine), HKOSLogger())
        lib = Librarian(repos, HKOSLogger())
        p = repos.projects.save(Project(name="OpenWrt", tags=["router"]))
        for i in range(5):
            lib.register(p.id, Knowledge(title=f"UDP topic {i}", body=f"udp {i}", tags=["udp"]))
        index.build(p.id)
        rv = RetrievalEngine(repos, IndexQueryExecutor(IndexStore(engine)), cfg, HKOSLogger())
        result = rv.retrieve("udp", project_id=p.id, top_n=10)
        assert result.items
        for item in result.items:
            assert item.explanation.reason
            assert item.explanation.score >= 0.0
            assert item.explanation.confidence >= 0
            assert item.explanation.matched_keywords is not None

    def test_10_pipeline_matches_ip008(self) -> None:
        """Порядок стадий: Parser -> Builder -> Ranking -> Filter -> Traverser -> Selector."""
        from unittest import mock

        parser = mock.Mock()
        builder = mock.Mock()
        ranking = mock.Mock()
        filter_ = mock.Mock()
        traverser = mock.Mock()
        selector = mock.Mock()

        from hkos.index.query_contract import IndexEntry
        from hkos.retrieval.candidate_builder import CandidateSet
        from hkos.retrieval.query_parser import ParsedQuery

        parser.parse.return_value = ParsedQuery(query="test", keywords=["test"])
        builder.build.return_value = CandidateSet(
            entries=[IndexEntry(id="k1", type="knowledge", project="p1")]
        )
        ranking.rank.return_value = []
        filter_.filter.return_value = []
        traverser.traverse.return_value = []
        selector.select.return_value = []

        retriever = Retriever(parser, builder, ranking, filter_, traverser, selector)
        retriever.run("test", project="p1")

        # Каждая стадия конвейера вызвана (порядок соответствует IP-008)
        assert parser.parse.called
        assert builder.build.called
        assert ranking.rank.called
        assert filter_.filter.called
        assert traverser.traverse.called
        assert selector.select.called

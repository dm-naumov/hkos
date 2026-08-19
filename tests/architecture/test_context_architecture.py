"""Architectural tests: Context Layer (IP-009).

Проверки:
1. Context Builder не импортирует StorageEngine.
2. Context Builder не импортирует IndexStore.
3. Context Builder не читает JSON.
4. Context Builder использует только RetrievalResult.
5. Snapshot только read-only.
6. Serializer выдаёт стабильный порядок.
7. Нет изменения RetrievalResult.
8. Нет обращения к Repository.list().
9. TokenEstimator не содержит захардкоженных коэффициентов.
10. Dependency Rule соблюдён.
"""

import os
import re
from pathlib import Path

CONTEXT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "context")


def _context_modules() -> list[str]:
    """Исходники модулей Context Layer (без docstring'ов)."""

    def strip_docstring(source: str) -> str:
        if source.startswith('"""'):
            end = source.find('"""', 3)
            if end > 0:
                return source[end + 3:]
        return source

    return [
        strip_docstring(open(os.path.join(CONTEXT_DIR, name), encoding="utf-8").read())
        for name in sorted(os.listdir(CONTEXT_DIR))
        if name.endswith(".py") and name != "__init__.py"
    ]


class TestContextArchitecture:
    """Архитектурные инварианты Context Builder (IP-009)."""

    def test_1_no_storage_engine(self) -> None:
        for source in _context_modules():
            assert "StorageEngine" not in source
            assert "storage_engine" not in source

    def test_2_no_index_store(self) -> None:
        for source in _context_modules():
            assert "IndexStore" not in source
            assert "index_store" not in source

    def test_3_no_json_reading(self) -> None:
        for source in _context_modules():
            assert "import json" not in source
            assert "json.load" not in source
            assert "open(" not in source

    def test_4_uses_only_retrieval_result(self) -> None:
        """Из hkos.retrieval импортируется только RetrievalResult."""
        for source in _context_modules():
            for line in source.splitlines():
                if line.startswith(("from hkos.retrieval", "import hkos.retrieval")):
                    assert "RetrievalResult" in line, f"не-результат импорт: {line.strip()}"

    def test_5_snapshot_read_only(self) -> None:
        from hkos.context.snapshot_loader import SnapshotDocument, SnapshotLoader

        loader_api = {m for m in dir(SnapshotLoader) if not m.startswith("_")}
        assert loader_api <= {"load", "reader"}
        doc_api = {m for m in dir(SnapshotDocument) if not m.startswith("_")}
        assert "write" not in " ".join(doc_api).lower()
        # Ни одного вызова записи в модулях контекста
        for source in _context_modules():
            assert ".write(" not in source
            assert "save(" not in source

    def test_6_serializer_stable_order(self) -> None:
        from hkos.context.context_serializer import ContextSerializer

        serializer = ContextSerializer()
        sections = serializer.sections
        expected = ["TASK", "PROJECT", "CURRENT STATE", "CANONICAL KNOWLEDGE",
                    "DECISIONS", "FAILURES", "ARTIFACTS", "CONFIGURATION",
                    "OPEN QUESTIONS"]
        assert list(sections) == expected

    def test_7_no_retrieval_result_mutation(self, tmp_path: Path) -> None:

        from hkos.context import ContextBuilder, SnapshotLoader
        from hkos.core.config import ConfigLoader
        from hkos.core.logger import HKOSLogger
        from hkos.core.version import VersionManager
        from hkos.index import IndexEngine, IndexQueryExecutor, IndexStore
        from hkos.repository.models import Knowledge, Project
        from hkos.repository.repository_manager import RepositoryManager
        from hkos.retrieval import RetrievalEngine
        from hkos.services.librarian import Librarian
        from hkos.storage import StorageEngine

        cfg = ConfigLoader(profile="development")
        cfg.load()
        engine = StorageEngine(
            root=str(tmp_path), config=cfg, logger=HKOSLogger(), version=VersionManager()
        )
        engine.initialize()
        repos = RepositoryManager(engine)
        lib = Librarian(repos, HKOSLogger())
        index = IndexEngine(repos, IndexStore(engine), HKOSLogger())
        p = repos.projects.save(Project(name="OpenWrt", tags=["router"]))
        lib.register(p.id, Knowledge(title="UDP topic", body="udp", tags=["udp"]))
        index.build(p.id)
        rv = RetrievalEngine(repos, IndexQueryExecutor(IndexStore(engine)), cfg, HKOSLogger())
        result = rv.retrieve("udp", project_id=p.id)
        snapshot_before = [i.as_dict() for i in result.items]
        cb = ContextBuilder(cfg, HKOSLogger(), loader=SnapshotLoader())
        cb.build(result, p.id)
        snapshot_after = [i.as_dict() for i in result.items]
        assert snapshot_before == snapshot_after

    def test_8_no_repository_list(self) -> None:
        for source in _context_modules():
            for line in source.splitlines():
                if re.search(r"\.list\s*\(", line):
                    assert False, f"Repository.list() usage: {line.strip()}"

    def test_9_token_estimator_no_hardcoded_coefficients(self) -> None:
        estimator = open(
            os.path.join(CONTEXT_DIR, "token_estimator.py"), encoding="utf-8"
        ).read()
        decimals = re.findall(r"\d+\.\d+", estimator)
        assert decimals == [], f"hardcoded coefficients: {decimals}"

    def test_10_dependency_rule(self) -> None:
        """Context Layer импортирует только: core, repository, retrieval
        (RetrievalResult), index (validation), services.librarian (константы).
        """
        allowed_prefixes = ("hkos.context", "hkos.core", "hkos.repository",
                            "hkos.retrieval", "hkos.index.validation",
                            "hkos.kernel",
                            "hkos.services.classification_policy",
                            "hkos.services.librarian.knowledge_status")
        for source in _context_modules():
            for line in source.splitlines():
                if line.startswith(("from hkos", "import hkos")):
                    module = line.split()[1]
                    if not any(module.startswith(p) for p in allowed_prefixes):
                        assert False, f"нарушение Dependency Rule: {line.strip()}"

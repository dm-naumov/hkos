"""DS-015 ЭТАП 2: API Contract Validation.

Публичные классы имеют документацию; методы описаны; интерфейсы
соответствуют текущему API (запрещено описывать несуществующие функции).
"""

import inspect
from pathlib import Path

from hkos.index import IndexEngine, IndexQueryExecutor
from hkos.integration.hermes.migration_commands import MigrationCommandRegistry
from hkos.integration.hermes.migration_tools import MigrationTools
from hkos.integration.hermes.security import AgentContext
from hkos.migration.migration_engine import MigrationEngine
from hkos.performance.performance_manager import PerformanceManager
from hkos.retrieval import RetrievalEngine
from hkos.services.librarian import Librarian
from hkos.services.memory_service import MemoryService
from hkos.snapshot import SnapshotEngine

PUBLIC_CLASSES = [
    MigrationEngine, RetrievalEngine, SnapshotEngine, IndexEngine,
    IndexQueryExecutor, Librarian, MemoryService, PerformanceManager,
    MigrationTools, MigrationCommandRegistry, AgentContext,
]


class TestApiContracts:
    """Контракты публичных API: документация + фактический состав."""

    def test_public_classes_documented(self) -> None:
        for cls in PUBLIC_CLASSES:
            doc = inspect.getdoc(cls)
            assert doc and len(doc) > 20, f"{cls.__name__} missing docstring"

    def test_public_methods_described(self) -> None:
        for cls in PUBLIC_CLASSES:
            for name, member in inspect.getmembers(cls, inspect.isfunction):
                if name.startswith("_"):
                    continue
                doc = inspect.getdoc(member)
                assert doc, f"{cls.__name__}.{name} missing description"

    def test_migration_engine_api_exact(self) -> None:
        """Ровно 7 методов + 2 lock-helper (DS-011 §6)."""
        methods = {
            name for name in vars(MigrationEngine)
            if not name.startswith("_") and callable(getattr(MigrationEngine, name))
        }
        assert methods == {
            "detect", "migrate", "rollback", "validate", "backup",
            "history", "status", "acquire_lock", "release_lock",
        }

    def test_retrieval_engine_api(self) -> None:
        """Публичный API Retrieval: retrieve + вспомогательные."""
        methods = {
            name for name in vars(RetrievalEngine)
            if not name.startswith("_") and callable(getattr(RetrievalEngine, name))
        }
        assert "retrieve" in methods
        assert not {"list", "walk", "scan"} & methods  # нет прямого доступа

    def test_no_nonexistent_api_in_docs(self) -> None:
        """Docs distinguish implemented index backends from nonexistent APIs."""
        docs_dir = Path(__file__).resolve().parents[3] / "docs"
        documents = {
            path.name: path.read_text(encoding="utf-8")
            for path in docs_dir.glob("*.md")
        }
        combined = "\n".join(documents.values()).lower()
        for term in ("event bus", "event sourcing", "Graph Search",
                     "Memory DB", "vector database"):
            assert term.lower() not in combined, (
                f"active docs mention nonexistent {term!r}")

        architecture = documents["architecture.md"].lower()
        assert "repository is the single source of truth" in architecture
        assert "sqlite" in architecture and "index" in architecture
        assert "sqlite storage backend" not in combined, (
            "SQLite is an index/query backend, not the Repository SSOT")

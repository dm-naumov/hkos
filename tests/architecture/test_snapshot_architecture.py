"""Architectural tests: Snapshot Layer (IP-010).

Проверки:
1. Snapshot не использует Retrieval.
2. Snapshot не использует Storage.
3. SnapshotLoader только read-only.
4. SnapshotDiff не использует Repository.
5. SnapshotBuilder использует только RepositoryManager (+ Entity Index).
6. Нет циклических зависимостей.
"""

import os

SNAPSHOT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "snapshot")


def _snapshot_modules() -> list[str]:
    """Исходники модулей Snapshot Layer (без docstring'ов)."""

    def strip_docstring(source: str) -> str:
        if source.startswith('"""'):
            end = source.find('"""', 3)
            if end > 0:
                return source[end + 3:]
        return source

    return [
        strip_docstring(open(os.path.join(SNAPSHOT_DIR, name), encoding="utf-8").read())
        for name in sorted(os.listdir(SNAPSHOT_DIR))
        if name.endswith(".py") and name != "__init__.py"
    ]


class TestSnapshotArchitecture:
    """Архитектурные инварианты Snapshot Engine (IP-010)."""

    def test_1_no_retrieval(self) -> None:
        for source in _snapshot_modules():
            assert "RetrievalEngine" not in source
            assert "retrieval_engine" not in source
            for line in source.splitlines():
                if line.startswith(("from hkos.retrieval", "import hkos.retrieval")):
                    assert False, f"Retrieval import: {line.strip()}"

    def test_2_no_storage(self) -> None:
        for source in _snapshot_modules():
            assert "StorageEngine" not in source
            assert "storage_engine" not in source
            for line in source.splitlines():
                if line.startswith(("from hkos.storage", "import hkos.storage")):
                    assert False, f"Storage import: {line.strip()}"

    def test_3_loader_read_only(self) -> None:
        from hkos.snapshot.snapshot_loader import SnapshotLoader

        api = {m for m in dir(SnapshotLoader) if not m.startswith("_")}
        assert api <= {"load_latest", "load_version", "persistence"}
        for source in _snapshot_modules():
            assert ".save(" not in source or "persistence" in source
            if "class SnapshotLoader" in source:
                body = source.split("class SnapshotLoader")[1]
                assert "append_history" not in body

    def test_4_diff_no_repository(self) -> None:
        import inspect

        from hkos.snapshot.snapshot_diff import SnapshotDiff

        source = inspect.getsource(SnapshotDiff)
        assert "self._repositories" not in source
        for line in source.splitlines():
            if line.startswith(("from hkos.repository", "import hkos.repository")):
                assert False, f"Repository import in diff: {line.strip()}"

    def test_5_builder_uses_repository_manager(self) -> None:
        import inspect

        from hkos.snapshot.snapshot_builder import SnapshotBuilder

        source = inspect.getsource(SnapshotBuilder)
        assert "RepositoryManager" in source
        assert "Retrieval" not in source.split('"""')[1] if '"""' in source else True
        # Builder не импортирует Retrieval
        for line in source.splitlines():
            if line.startswith(("from hkos.retrieval", "import hkos.retrieval")):
                assert False, f"Retrieval import in builder: {line.strip()}"

    def test_6_no_cycles(self) -> None:
        """Граф зависимостей Snapshot Layer: snapshot -> {context, repository, index, core};
        context НЕ импортирует snapshot.
        """
        snapshot_imports: set[str] = set()
        for name in os.listdir(SNAPSHOT_DIR):
            if not name.endswith(".py"):
                continue
            for line in open(os.path.join(SNAPSHOT_DIR, name), encoding="utf-8"):
                if line.startswith(("from hkos.", "import hkos.")):
                    snapshot_imports.add(line.split()[1].split(".")[1])
        # context не должен импортировать snapshot (цикл)
        context_files = os.path.join(os.path.dirname(__file__), "..", "..", "context")
        for name in os.listdir(context_files):
            if not name.endswith(".py"):
                continue
            for line in open(os.path.join(context_files, name), encoding="utf-8"):
                if line.startswith(("from hkos.snapshot", "import hkos.snapshot")):
                    assert False, f"Cycle: context imports snapshot ({line.strip()})"
        # допустимые зависимости snapshot-слоя (services — константы
        # статусов knowledge_status, как у Context Layer; kernel — общий
        # тип SnapshotDocument (Post-Audit Refinement); snapshot —
        # внутрипакетные импорты)
        allowed = {"context", "core", "repository", "index", "services",
                   "kernel", "snapshot"}
        assert snapshot_imports <= allowed, f"Unexpected deps: {snapshot_imports - allowed}"

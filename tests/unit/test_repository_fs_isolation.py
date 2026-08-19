"""FS-isolation tests: Repository не обращается к файловой системе напрямую.

IP-003 §11: репозитории обязаны работать исключительно через StorageEngine.
Два уровня проверки:
1. Статический: в исходниках hkos/repository/ отсутствуют запрещённые API
   (open, pathlib, os.remove/mkdir/listdir, json.load/dump).
2. Динамический: CRUD проходит при заблокированных прямых API ФС.
3. Mock StorageEngine: фиксация вызовов — только методы StorageEngine.
"""

import json as json_mod
import os
from pathlib import Path
from unittest import mock

from _pytest.monkeypatch import MonkeyPatch

from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.repository.knowledge_repository import KnowledgeRepository
from hkos.repository.models import Knowledge
from hkos.storage import StorageEngine

FORBIDDEN_PATTERNS = [
    "import pathlib",
    "from pathlib",
    "json.load(",
    "json.dump(",
    "os.remove",
    "os.mkdir(",
    "os.listdir",
    "open(",
]


class TestRepositoryFsIsolation:
    """Repository должен проходить CRUD при заблокированных прямых API ФС."""

    def _engine(self, tmp_path: Path) -> StorageEngine:
        cfg = ConfigLoader(profile="development")
        cfg.load()
        engine = StorageEngine(
            root=str(tmp_path), config=cfg, logger=HKOSLogger(), version=VersionManager()
        )
        engine.initialize()
        return engine

    def test_no_forbidden_api_in_source(self) -> None:
        """Статическая проверка исходников пакета repository."""
        repo_dir = os.path.join(os.path.dirname(__file__), "..", "..", "repository")
        offenders = []
        for name in sorted(os.listdir(repo_dir)):
            if not name.endswith(".py"):
                continue
            source = open(os.path.join(repo_dir, name), encoding="utf-8").read()
            for pattern in FORBIDDEN_PATTERNS:
                if pattern in source:
                    offenders.append(f"{name}: {pattern}")
        assert offenders == []

    def _block(self, monkeypatch: MonkeyPatch) -> None:
        """Заблокировать прямые API, не используемые StorageEngine."""

        def fail(*args: object, **kwargs: object) -> None:
            raise AssertionError("Direct filesystem access from Repository!")

        monkeypatch.setattr(json_mod, "load", fail)
        monkeypatch.setattr(json_mod, "dump", fail)

    def test_crud_with_blocked_direct_api(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        engine = self._engine(tmp_path)
        repo = KnowledgeRepository(engine, engine.json_store)
        repo.storage.mkdir(repo.storage.path_manager.project(engine.root, "p1"))
        self._block(monkeypatch)

        k = repo.create(Knowledge(project="p1", title="T"))
        assert repo.load("p1", k.id).title == "T"
        k.title = "T2"
        repo.update(k)
        assert repo.load("p1", k.id).title == "T2"
        assert repo.count("p1") == 1
        repo.delete("p1", k.id)
        assert not repo.exists("p1", k.id)

    def test_repository_calls_storage_only(self, tmp_path: Path) -> None:
        engine = self._engine(tmp_path)
        storage = mock.Mock(spec=StorageEngine)
        storage.root = engine.root
        storage.exists.return_value = False
        storage.json_store = engine.json_store
        repo = KnowledgeRepository(storage, engine.json_store)

        repo.save(Knowledge(project="p1", title="T"))

        assert storage.mkdir.called
        assert storage.write_json.called
        path, doc = storage.write_json.call_args.args
        assert doc["schema"] == "HKOS-1.0"
        assert doc["type"] == "knowledge"
        for call in storage.mock_calls:
            assert call[0].split(".")[0] in {
                "mkdir", "write_json", "exists", "read_json", "delete", "list",
            }

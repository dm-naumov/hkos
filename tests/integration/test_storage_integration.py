"""Integration tests: полный жизненный цикл Storage Engine (DS-002 §16).

initialize -> mkdir -> write_json -> read_json -> update_json -> list -> delete
"""

import os
from pathlib import Path
from typing import Any

from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.storage import FileStore, JSONStore, PathManager, StorageEngine
from hkos.storage.exceptions import StorageSerializationError


class TestStorageIntegration:
    """Full storage cycle on a temporary workspace."""

    def _engine(self, tmp_path: Path) -> StorageEngine:
        cfg = ConfigLoader(profile="development")
        cfg.load()
        return StorageEngine(
            root=str(tmp_path),
            config=cfg,
            logger=HKOSLogger(),
            version=VersionManager(),
        )

    def test_full_cycle(self, tmp_path: Path) -> None:
        engine = self._engine(tmp_path)
        engine.initialize()

        # mkdir
        project_dir = PathManager.project(str(tmp_path), "OpenWrt")
        engine.mkdir(project_dir)

        # write_json
        doc_path = PathManager.project_file(str(tmp_path), "OpenWrt")
        store = JSONStore(HKOSLogger(), FileStore(HKOSLogger()))
        engine.write_json(
            doc_path,
            store.create_envelope(
                {"id": "openwrt", "name": "OpenWrt", "status": "active"},
                "project",
            ),
        )

        # read_json
        loaded = engine.read_json(doc_path)
        assert loaded["data"]["name"] == "OpenWrt"

        # update_json
        def updater(doc: dict[str, Any]) -> dict[str, Any]:
            data = dict(doc["data"])
            data["status"] = "archived"
            return {**doc, "data": data}

        engine.update_json(doc_path, updater)
        assert engine.read_json(doc_path)["data"]["status"] == "archived"

        # list
        assert engine.list(project_dir) == ["project.json"]

        # delete
        engine.delete(doc_path)
        assert not engine.exists(doc_path)
        assert engine.health()["status"] == "PASS"

    def test_atomic_write_preserves_data_on_failure(self, tmp_path: Path) -> None:
        engine = self._engine(tmp_path)
        engine.initialize()
        path = str(tmp_path / "obj.json")
        store = JSONStore(HKOSLogger(), FileStore(HKOSLogger()))
        engine.write_json(path, store.create_envelope({"v": 1}, "project"))

        try:
            engine.write_json(path, {"broken": True})
        except StorageSerializationError:
            pass

        assert engine.read_json(path)["data"] == {"v": 1}

    def test_relative_paths_across_cycle(self, tmp_path: Path) -> None:
        engine = self._engine(tmp_path)
        engine.initialize()
        engine.mkdir("project/campaigns")
        store = JSONStore(HKOSLogger(), FileStore(HKOSLogger()))
        engine.write_json(
            "project/campaigns/meta.json",
            store.create_envelope({"goal": "test"}, "campaign"),
        )
        assert os.path.exists(str(tmp_path / "project" / "campaigns" / "meta.json"))
        assert engine.read_json("project/campaigns/meta.json")["data"]["goal"] == "test"

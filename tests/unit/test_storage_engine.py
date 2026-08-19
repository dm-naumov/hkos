"""Unit tests for StorageEngine facade (DS-002)."""

import os
from pathlib import Path
from typing import Any

import pytest

from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.storage import FileStore, JSONStore, StorageEngine
from hkos.storage.exceptions import StorageSerializationError


class TestStorageEngine:
    """Test suite for StorageEngine public API."""

    def _engine(self, tmp_path: Path, root: str | None = None) -> StorageEngine:
        cfg = ConfigLoader(profile="development")
        cfg.load()
        return StorageEngine(
            root=root if root is not None else str(tmp_path),
            config=cfg,
            logger=HKOSLogger(),
            version=VersionManager(),
        )

    def _doc(self, data: dict[str, Any]) -> dict[str, Any]:
        store = JSONStore(HKOSLogger(), FileStore(HKOSLogger()))
        return store.create_envelope(data, "project")

    def test_initialize_creates_root(self, tmp_path: Path) -> None:
        engine = self._engine(tmp_path)
        engine.initialize()
        assert os.path.isdir(engine.root)
        assert engine.is_initialized

    def test_health_pass_after_init(self, tmp_path: Path) -> None:
        engine = self._engine(tmp_path)
        engine.initialize()
        report = engine.health()
        assert report["status"] == "PASS"
        assert report["initialized"] is True
        assert report["version"] == "1.0.1"

    def test_health_fail_without_root(self, tmp_path: Path) -> None:
        engine = self._engine(tmp_path, root=str(tmp_path / "missing"))
        report = engine.health()
        assert report["status"] == "FAIL"

    def test_mkdir_and_exists(self, tmp_path: Path) -> None:
        engine = self._engine(tmp_path)
        engine.initialize()
        target = str(tmp_path / "proj")
        engine.mkdir(target)
        assert engine.exists(target)
        assert not engine.exists(str(tmp_path / "absent"))

    def test_write_read_json_roundtrip(self, tmp_path: Path) -> None:
        engine = self._engine(tmp_path)
        engine.initialize()
        path = str(tmp_path / "obj.json")
        engine.write_json(path, self._doc({"name": "OpenWrt"}))
        assert engine.read_json(path)["data"] == {"name": "OpenWrt"}

    def test_update_json(self, tmp_path: Path) -> None:
        engine = self._engine(tmp_path)
        engine.initialize()
        path = str(tmp_path / "obj.json")
        engine.write_json(path, self._doc({"status": "new"}))

        def updater(doc: dict[str, Any]) -> dict[str, Any]:
            data = dict(doc["data"])
            data["status"] = "active"
            return {**doc, "data": data}

        engine.update_json(path, updater)
        assert engine.read_json(path)["data"]["status"] == "active"

    def test_delete_removes_file(self, tmp_path: Path) -> None:
        engine = self._engine(tmp_path)
        engine.initialize()
        path = str(tmp_path / "obj.json")
        engine.write_json(path, self._doc({}))
        engine.delete(path)
        assert not engine.exists(path)

    def test_list_sorted(self, tmp_path: Path) -> None:
        engine = self._engine(tmp_path)
        engine.initialize()
        engine.write_json(str(tmp_path / "b.json"), self._doc({}))
        engine.write_json(str(tmp_path / "a.json"), self._doc({}))
        assert engine.list(str(tmp_path)) == ["a.json", "b.json"]

    def test_relative_path_resolution(self, tmp_path: Path) -> None:
        engine = self._engine(tmp_path)
        engine.initialize()
        engine.mkdir("proj")
        engine.write_json("proj/doc.json", self._doc({"id": "x"}))
        assert engine.exists("proj/doc.json")
        assert engine.read_json("proj/doc.json")["data"] == {"id": "x"}

    def test_default_root_from_config(self, tmp_path: Path) -> None:
        cfg = ConfigLoader(profile="development")
        cfg.load()
        engine = StorageEngine(
            root=None, config=cfg, logger=HKOSLogger(), version=VersionManager()
        )
        expected = os.path.abspath(cfg.get("hkos.root", "./hkos"))
        assert engine.root == expected

    def test_write_requires_envelope(self, tmp_path: Path) -> None:
        engine = self._engine(tmp_path)
        engine.initialize()
        with pytest.raises(StorageSerializationError):
            engine.write_json(str(tmp_path / "bad.json"), {"data": {}})

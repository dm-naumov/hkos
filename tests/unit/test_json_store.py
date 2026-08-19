"""Unit tests for JSONStore (DS-002, HKOS-08)."""

from pathlib import Path
from typing import Any

import pytest

from hkos.core.logger import HKOSLogger
from hkos.storage.exceptions import (
    StorageMigrationRequired,
    StorageReadError,
    StorageSerializationError,
)
from hkos.storage.file_store import FileStore
from hkos.storage.json_store import JSONStore


class TestJSONStore:
    """Test suite for JSONStore serialization and envelope handling."""

    def _store(self, tmp_path: Path) -> JSONStore:
        fs = FileStore(HKOSLogger())
        return JSONStore(HKOSLogger(), fs)

    def test_serialize_deterministic(self) -> None:
        a = JSONStore.serialize({"b": 1, "a": 2})
        b = JSONStore.serialize({"a": 2, "b": 1})
        assert a == b

    def test_serialize_pretty(self) -> None:
        text = JSONStore.serialize({"a": 1})
        assert "\n" in text
        assert "  " in text

    def test_serialize_utf8(self) -> None:
        text = JSONStore.serialize({"title": "инженерные знания"})
        assert "инженерные знания" in text

    def test_deserialize_roundtrip(self) -> None:
        obj = JSONStore.deserialize('{"a": 1}')
        assert obj == {"a": 1}

    def test_deserialize_invalid_raises(self) -> None:
        with pytest.raises(StorageSerializationError):
            JSONStore.deserialize("{broken")

    def test_validate_envelope_ok(self, tmp_path: Path) -> None:
        store = self._store(tmp_path)
        doc = store.create_envelope({"id": "x"}, "project")
        assert store.validate_envelope(doc) == 1

    def test_validate_envelope_missing_schema(self, tmp_path: Path) -> None:
        store = self._store(tmp_path)
        with pytest.raises(StorageSerializationError):
            store.validate_envelope({"version": 1, "data": {}})

    def test_validate_envelope_missing_version(self, tmp_path: Path) -> None:
        store = self._store(tmp_path)
        with pytest.raises(StorageSerializationError):
            store.validate_envelope({"schema": "HKOS-1.0", "data": {}})

    def test_validate_envelope_unsupported_version(self, tmp_path: Path) -> None:
        store = self._store(tmp_path)
        doc = store.create_envelope({}, "project", version=2)
        with pytest.raises(StorageMigrationRequired):
            store.validate_envelope(doc)

    def test_create_envelope_fields(self, tmp_path: Path) -> None:
        store = self._store(tmp_path)
        doc = store.create_envelope({"id": "x"}, "knowledge")
        assert doc["schema"] == "HKOS-1.0"
        assert doc["type"] == "knowledge"
        assert doc["version"] == 1
        assert doc["data"] == {"id": "x"}
        assert doc["created_at"]
        assert doc["updated_at"]

    def test_write_read_roundtrip(self, tmp_path: Path) -> None:
        store = self._store(tmp_path)
        path = str(tmp_path / "obj.json")
        doc = store.create_envelope({"name": "OpenWrt"}, "project")
        store.write(path, doc)
        loaded = store.read(path)
        assert loaded["data"] == {"name": "OpenWrt"}
        assert loaded["type"] == "project"

    def test_write_preserves_version(self, tmp_path: Path) -> None:
        store = self._store(tmp_path)
        path = str(tmp_path / "obj.json")
        doc = store.create_envelope({}, "project", version=1)
        store.write(path, doc)
        loaded = store.read(path)
        assert loaded["version"] == 1

    def test_write_requires_envelope(self, tmp_path: Path) -> None:
        store = self._store(tmp_path)
        path = str(tmp_path / "obj.json")
        with pytest.raises(StorageSerializationError):
            store.write(path, {"data": {"x": 1}})

    def test_update_applies_updater(self, tmp_path: Path) -> None:
        store = self._store(tmp_path)
        path = str(tmp_path / "obj.json")
        doc = store.create_envelope({"status": "new"}, "project")
        store.write(path, doc)

        def updater(doc: dict[str, Any]) -> dict[str, Any]:
            data = dict(doc["data"])
            data["status"] = "active"
            return {**doc, "data": data}

        store.update(path, updater)
        assert store.read(path)["data"]["status"] == "active"

    def test_read_missing_raises(self, tmp_path: Path) -> None:
        with pytest.raises(StorageReadError):
            self._store(tmp_path).read(str(tmp_path / "missing.json"))

    def test_read_unsupported_version_raises(self, tmp_path: Path) -> None:
        store = self._store(tmp_path)
        fs = FileStore(HKOSLogger())
        path = str(tmp_path / "obj.json")
        doc = store.create_envelope({}, "project", version=3)
        # Запись в обход валидации write() — имитация документа будущей версии
        fs.write_text(path, store.serialize(doc))
        with pytest.raises(StorageMigrationRequired):
            store.read(path)

    def test_write_unsupported_version_raises(self, tmp_path: Path) -> None:
        store = self._store(tmp_path)
        path = str(tmp_path / "obj.json")
        doc = store.create_envelope({}, "project", version=3)
        with pytest.raises(StorageMigrationRequired):
            store.write(path, doc)

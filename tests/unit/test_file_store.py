"""Unit tests for FileStore (DS-002)."""

from pathlib import Path

import pytest

from hkos.core.logger import HKOSLogger
from hkos.storage.exceptions import StorageReadError, StorageWriteError
from hkos.storage.file_store import FileStore


class TestFileStore:
    """Test suite for FileStore low-level filesystem operations."""

    def _store(self) -> FileStore:
        return FileStore(HKOSLogger())

    def test_exists_false_for_missing(self, tmp_path: Path) -> None:
        assert self._store().exists(str(tmp_path / "nope")) is False

    def test_exists_true_after_create(self, tmp_path: Path) -> None:
        store = self._store()
        store.write_text(str(tmp_path / "a.txt"), "x")
        assert store.exists(str(tmp_path / "a.txt")) is True

    def test_mkdir_creates_nested(self, tmp_path: Path) -> None:
        store = self._store()
        target = str(tmp_path / "a" / "b" / "c")
        store.mkdir(target)
        assert store.is_dir(target) is True

    def test_write_read_roundtrip(self, tmp_path: Path) -> None:
        store = self._store()
        path = str(tmp_path / "data.txt")
        store.write_text(path, "содержимое")
        assert store.read_text(path) == "содержимое"

    def test_read_missing_raises(self, tmp_path: Path) -> None:
        with pytest.raises(StorageReadError):
            self._store().read_text(str(tmp_path / "missing.txt"))

    def test_is_file(self, tmp_path: Path) -> None:
        store = self._store()
        path = str(tmp_path / "f.txt")
        store.write_text(path, "x")
        assert store.is_file(path) is True
        assert store.is_dir(path) is False

    def test_delete_removes_file(self, tmp_path: Path) -> None:
        store = self._store()
        path = str(tmp_path / "f.txt")
        store.write_text(path, "x")
        store.delete(path)
        assert store.exists(path) is False

    def test_delete_missing_raises(self, tmp_path: Path) -> None:
        with pytest.raises(StorageWriteError):
            self._store().delete(str(tmp_path / "missing.txt"))

    def test_delete_directory_raises(self, tmp_path: Path) -> None:
        store = self._store()
        target = str(tmp_path / "dir")
        store.mkdir(target)
        with pytest.raises(StorageWriteError):
            store.delete(target)

    def test_list_sorted(self, tmp_path: Path) -> None:
        store = self._store()
        for name in ["b.txt", "a.txt"]:
            store.write_text(str(tmp_path / name), "x")
        assert store.list(str(tmp_path)) == ["a.txt", "b.txt"]

    def test_list_missing_raises(self, tmp_path: Path) -> None:
        with pytest.raises(StorageReadError):
            self._store().list(str(tmp_path / "missing"))

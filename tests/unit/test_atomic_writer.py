"""Unit tests for AtomicWriter (DS-002)."""

import json
import os
from pathlib import Path

import pytest

from hkos.core.logger import HKOSLogger
from hkos.storage.atomic_writer import AtomicWriter
from hkos.storage.exceptions import StorageSerializationError, StorageWriteError


class TestAtomicWriter:
    """Test suite for AtomicWriter atomic file writes."""

    def _writer(self) -> AtomicWriter:
        return AtomicWriter(HKOSLogger())

    def test_write_creates_file(self, tmp_path: Path) -> None:
        target = str(tmp_path / "file.txt")
        self._writer().write(target, "hello")
        assert os.path.isfile(target)
        with open(target, encoding="utf-8") as f:
            assert f.read() == "hello"

    def test_write_overwrites_atomically(self, tmp_path: Path) -> None:
        target = str(tmp_path / "file.txt")
        writer = self._writer()
        writer.write(target, "first")
        writer.write(target, "second")
        with open(target, encoding="utf-8") as f:
            assert f.read() == "second"

    def test_write_missing_dir_raises(self, tmp_path: Path) -> None:
        target = str(tmp_path / "missing" / "file.txt")
        with pytest.raises(StorageWriteError):
            self._writer().write(target, "x")

    def test_no_temp_files_left(self, tmp_path: Path) -> None:
        target = str(tmp_path / "file.txt")
        self._writer().write(target, "x")
        leftovers = [n for n in os.listdir(tmp_path) if n.endswith(".tmp")]
        assert leftovers == []

    def test_valid_json_passes_validation(self, tmp_path: Path) -> None:
        target = str(tmp_path / "doc.json")
        self._writer().write(target, '{"a": 1}', validate_json=True)
        with open(target, encoding="utf-8") as f:
            assert json.load(f) == {"a": 1}

    def test_invalid_json_raises(self, tmp_path: Path) -> None:
        target = str(tmp_path / "doc.json")
        with pytest.raises(StorageSerializationError):
            self._writer().write(target, "not json", validate_json=True)

    def test_invalid_json_creates_no_file(self, tmp_path: Path) -> None:
        target = str(tmp_path / "doc.json")
        with pytest.raises(StorageSerializationError):
            self._writer().write(target, "not json", validate_json=True)
        assert not os.path.exists(target)

    def test_failed_validation_keeps_original(self, tmp_path: Path) -> None:
        target = str(tmp_path / "doc.json")
        writer = self._writer()
        writer.write(target, '{"ok": true}', validate_json=True)
        with pytest.raises(StorageSerializationError):
            writer.write(target, "broken", validate_json=True)
        with open(target, encoding="utf-8") as f:
            assert json.load(f) == {"ok": True}

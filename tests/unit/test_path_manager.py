"""Unit tests for PathManager (DS-002)."""

import pytest

from hkos.storage.exceptions import StoragePathError
from hkos.storage.path_manager import PathManager


class TestPathManager:
    """Test suite for PathManager path building."""

    def test_workspace_normalized(self) -> None:
        assert PathManager.workspace("/tmp/a/../b") == "/tmp/b"

    def test_project_path(self) -> None:
        path = PathManager.project("/ws", "OpenWrt")
        assert path == "/ws/projects/OpenWrt"

    def test_project_file_path(self) -> None:
        path = PathManager.project_file("/ws", "OpenWrt")
        assert path == "/ws/projects/OpenWrt/project.json"

    def test_campaign_path(self) -> None:
        path = PathManager.campaign("/ws", "OpenWrt", "campaign-0001")
        assert path == "/ws/projects/OpenWrt/campaigns/campaign-0001"

    def test_knowledge_path(self) -> None:
        path = PathManager.knowledge("/ws", "OpenWrt")
        assert path == "/ws/projects/OpenWrt/knowledge"

    def test_snapshot_path(self) -> None:
        path = PathManager.snapshot("/ws", "OpenWrt")
        assert path == "/ws/projects/OpenWrt/snapshots"

    def test_global_dir(self) -> None:
        path = PathManager.global_dir("/ws")
        assert path == "/ws/global"

    def test_empty_project_rejected(self) -> None:
        with pytest.raises(StoragePathError):
            PathManager.project("/ws", "")

    def test_parent_traversal_rejected(self) -> None:
        with pytest.raises(StoragePathError):
            PathManager.project("/ws", "..")

    def test_dot_rejected(self) -> None:
        with pytest.raises(StoragePathError):
            PathManager.project("/ws", ".")

    def test_separator_rejected(self) -> None:
        with pytest.raises(StoragePathError):
            PathManager.campaign("/ws", "OpenWrt", "a/b")

    def test_backslash_rejected(self) -> None:
        with pytest.raises(StoragePathError):
            PathManager.knowledge("/ws", "a\\b")

"""Integration tests: полный жизненный цикл проекта (DS-004 §16, IP-004 этап 09).

Create -> Validate -> Open -> Rename -> Close -> Archive -> Delete

Также проверяется отсутствие прямого обращения к Storage Engine:
1. статический скан исходников hkos/services/ (запрещённые API отсутствуют);
2. операционный прогон с заблокированными прямыми API (json.load/json.dump).
"""

import json as json_mod
import os
from pathlib import Path

from _pytest.monkeypatch import MonkeyPatch

from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.repository.repository_manager import RepositoryManager
from hkos.services.project_manager import ProjectManager
from hkos.services.project_state import (
    PROJECT_STATE_ACTIVE,
    PROJECT_STATE_ARCHIVED,
    PROJECT_STATE_PAUSED,
)
from hkos.storage import StorageEngine

FORBIDDEN_IN_SERVICES = [
    "StorageEngine",
    "JSONStore",
    "FileStore",
    "AtomicWriter",
    "PathManager",
    "os.path",
    "os.mkdir",
    "os.remove",
    "os.listdir",
    "import json",
    "from json",
    "import pathlib",
    "from pathlib",
]


class TestProjectIntegration:
    """Full project lifecycle scenario."""

    def _manager(self, tmp_path: Path) -> tuple[ProjectManager, StorageEngine]:
        cfg = ConfigLoader(profile="development")
        cfg.load()
        engine = StorageEngine(
            root=str(tmp_path), config=cfg, logger=HKOSLogger(), version=VersionManager()
        )
        engine.initialize()
        return ProjectManager(RepositoryManager(engine), HKOSLogger()), engine

    def test_full_scenario(self, tmp_path: Path) -> None:
        manager, engine = self._manager(tmp_path)

        # Create
        project = manager.create(
            name="OpenWrt", description="Router OS", owner="dm", tags=["networking"]
        )
        assert manager.exists(project.id)
        assert engine.exists(f"projects/{project.id}/project.json")

        # Validate
        assert manager.validate(project.id).valid is True

        # Open
        assert manager.open(project.id).status == PROJECT_STATE_ACTIVE

        # Rename
        renamed = manager.rename(project.id, "OpenWrt 25.12")
        assert renamed.name == "OpenWrt 25.12"
        assert renamed.id == project.id

        # Close
        assert manager.close(project.id).status == PROJECT_STATE_PAUSED

        # Archive
        assert manager.archive(project.id).status == PROJECT_STATE_ARCHIVED

        # Delete
        manager.delete(project.id)
        assert not manager.exists(project.id)

    def test_no_forbidden_api_in_services_source(self) -> None:
        """Статическая проверка: сервисный слой не использует Storage напрямую."""
        services_dir = os.path.join(
            os.path.dirname(__file__), "..", "..", "services"
        )
        offenders = []
        for name in sorted(os.listdir(services_dir)):
            if not name.endswith(".py"):
                continue
            source = open(os.path.join(services_dir, name), encoding="utf-8").read()
            for pattern in FORBIDDEN_IN_SERVICES:
                if pattern in source:
                    offenders.append(f"{name}: {pattern}")
        assert offenders == []

    def test_scenario_with_blocked_direct_api(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        manager, _ = self._manager(tmp_path)

        def fail(*args: object, **kwargs: object) -> None:
            raise AssertionError("Direct filesystem access from services!")

        monkeypatch.setattr(json_mod, "load", fail)
        monkeypatch.setattr(json_mod, "dump", fail)

        project = manager.create(name="OpenWrt")
        manager.open(project.id)
        manager.rename(project.id, "OpenWrt v2")
        manager.close(project.id)
        manager.archive(project.id)
        assert manager.validate(project.id).valid is True
        manager.delete(project.id)

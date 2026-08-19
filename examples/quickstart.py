"""HKOS quick start demo.

Runs the full knowledge pipeline on a throwaway corpus:
    init -> project -> campaign -> register (Librarian) -> canonicalize
    -> index build -> retrieve -> context-free retrieval -> snapshot

Usage (from the repository root):
    python examples/quickstart.py

Everything lives under a temporary directory; no real data is touched.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.index import IndexCache, IndexEngine, IndexQueryExecutor, IndexStore
from hkos.repository.models import Knowledge
from hkos.repository.repository_manager import RepositoryManager
from hkos.retrieval import RetrievalEngine
from hkos.services.campaign_manager import CampaignManager
from hkos.services.librarian import Librarian
from hkos.services.project_manager import ProjectManager
from hkos.snapshot import SnapshotEngine
from hkos.storage import StorageEngine


class MemoryPersistence:
    """Minimal in-memory SnapshotPersistence port (demo only)."""

    def __init__(self) -> None:
        self._latest: dict[str, dict[str, object]] = {}
        self._history: dict[str, list[dict[str, object]]] = {}

    def latest(self, project: str) -> dict[str, object] | None:
        return self._latest.get(project)

    def version(self, project: str, version: str) -> dict[str, object] | None:
        return self._latest.get(project)

    def save(self, project: str, doc: dict[str, object]) -> str:
        self._latest[project] = doc
        return str(doc.get("snapshot_id", ""))

    def history(self, project: str) -> list[dict[str, object]]:
        return self._history.get(project, [])

    def append_history(self, project: str, entry: dict[str, object]) -> None:
        self._history.setdefault(project, []).append(entry)


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="hkos-demo-"))
    print(f"data root: {root}")

    cfg = ConfigLoader()
    cfg.load()
    engine = StorageEngine(
        root=str(root), config=cfg, logger=HKOSLogger(), version=VersionManager()
    )
    engine.initialize()

    repos = RepositoryManager(engine)
    projects = ProjectManager(repos, HKOSLogger())
    campaigns = CampaignManager(repos, HKOSLogger())
    librarian = Librarian(repos, HKOSLogger())

    # Project + campaign
    project = projects.create(name="Demo", description="quickstart demo", tags=["demo"])
    campaign = campaigns.create(project.id, goal="Learn HKOS by example")
    print(f"project: {project.id}")
    print(f"campaign: {campaign.id}")

    # Register knowledge through the Librarian (the only write path)
    items = [
        Knowledge(
            title="TCP redirect works via nftables",
            body="meta l4proto tcp redirect to :12345",
            tags=["tcp", "nftables"],
        ),
        Knowledge(
            title="UDP traffic bypasses the proxy",
            body="cause: rule matches tcp only; fix: add tproxy rule",
            kind="negative",
        ),
        Knowledge(
            title="Decision: use fwmark for routing",
            body="fwmark 0x1 lookup 100 is stable across reboots",
            category="DECISION",
        ),
    ]
    ids = [librarian.register(project.id, k).id for k in items]
    for k_id in ids:
        librarian.canonicalize(project.id, k_id)
    print(f"knowledge registered & canonicalized: {len(ids)}")

    # Build the index and retrieve
    store = IndexStore(engine)
    cache = IndexCache()
    index = IndexEngine(repos, store, HKOSLogger(), cache=cache)
    index.build(project.id)
    qc = IndexQueryExecutor(store, cache=cache)
    retrieval = RetrievalEngine(repos, qc, cfg, HKOSLogger())

    result = retrieval.retrieve("udp proxy", project_id=project.id, top_n=5)
    print(f"retrieval: {len(result.items)} item(s) for 'udp proxy'")
    for item in result.items:
        print(f"  [{item.entity.category}] {item.entity.title}")

    # Snapshot the current state
    snapshots = SnapshotEngine(
        repos, MemoryPersistence(), HKOSLogger(), index_provider=qc.snapshot
    )
    snapshot = snapshots.create(
        project.id, reason="demo", comment="quickstart", author="demo", force=True
    )
    print(f"snapshot: {snapshot.snapshot_id} knowledge={snapshot.statistics.get('knowledge')}")

    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

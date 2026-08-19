#!/usr/bin/env python3
"""HKOS demo corpus generator.

Generates a deterministic, throwaway knowledge corpus (no real data) and
prints retrieval/snapshot results. Same machinery the benchmarks use.

Usage (from the repository root):
    python3 scripts/generate_demo.py [--projects N] [--per-project M]

Defaults: 2 projects x 10 knowledge items each.
"""

from __future__ import annotations

import argparse
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
    """In-memory SnapshotPersistence port (demo only)."""

    def __init__(self) -> None:
        self._latest: dict[str, dict[str, object]] = {}

    def latest(self, project: str) -> dict[str, object] | None:
        return self._latest.get(project)

    def version(self, project: str, version: str) -> dict[str, object] | None:
        return self._latest.get(project)

    def save(self, project: str, doc: dict[str, object]) -> str:
        self._latest[project] = doc
        return str(doc.get("snapshot_id", ""))

    def history(self, project: str) -> list[dict[str, object]]:
        return []

    def append_history(self, project: str, entry: dict[str, object]) -> None:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(prog="hkos generate-demo")
    parser.add_argument("--projects", type=int, default=2)
    parser.add_argument("--per-project", type=int, default=10)
    args = parser.parse_args()

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

    total = 0
    for p_index in range(args.projects):
        project = projects.create(
            name=f"Project-{p_index}", description="demo corpus", tags=["demo"])
        campaigns.create(project.id, goal=f"Demo campaign {p_index}")
        for k_index in range(args.per_project):
            kind = "negative" if k_index % 5 == 0 else "fact"
            librarian.register(project.id, Knowledge(
                title=f"P{p_index}K{k_index}fact udp proxy",
                body=("cause: rule matches tcp only; fix: add tproxy rule"
                      if kind == "negative"
                      else "meta l4proto tcp redirect to :12345"),
                tags=["udp", "proxy", f"p{p_index}"],
                kind=kind,
            ))
        total += args.per_project
    print(f"projects={args.projects} knowledge={total}")

    # Canonicalize everything, build indexes, snapshot
    for p in projects.list():
        for k in repos.knowledge.list(p.id):
            librarian.canonicalize(p.id, k.id)

    store = IndexStore(engine)
    cache = IndexCache()
    index = IndexEngine(repos, store, HKOSLogger(), cache=cache)
    qc = IndexQueryExecutor(store, cache=cache)
    for p in projects.list():
        index.build(p.id)
    print(f"indexes built: {len(projects.list())}")

    snapshots = SnapshotEngine(
        repos, MemoryPersistence(), HKOSLogger(), index_provider=qc.snapshot)
    for p in projects.list():
        snapshots.create(p.id, reason="demo", author="generate-demo", force=True)
    print(f"snapshots created: {len(projects.list())}")

    # Retrieve a negative-knowledge query
    retrieval = RetrievalEngine(repos, qc, cfg, HKOSLogger())
    pid = projects.list()[0].id
    result = retrieval.retrieve("udp proxy", project_id=pid, top_n=3)
    print(f"retrieval 'udp proxy' -> {len(result.items)} item(s):")
    for item in result.items:
        print(f"  [{item.entity.category}] {item.entity.title}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

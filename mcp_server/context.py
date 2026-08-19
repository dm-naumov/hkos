"""HKOS MCP server context: composition of the public HKOS APIs.

Thin wiring only — zero business logic. Mirrors the documented production
composition (see the production-bootstrap reference in the hkos-development
skill and scripts/doctor_cli.py).
"""

from __future__ import annotations

from dataclasses import dataclass

from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.index import IndexCache, IndexEngine, IndexQueryExecutor, IndexStore
from hkos.integration.hermes.doctor import HkosDoctor
from hkos.mcp_server.persistence import FileSnapshotPersistence
from hkos.repository.repository_manager import RepositoryManager
from hkos.retrieval import RetrievalEngine
from hkos.services.campaign_manager import CampaignManager
from hkos.services.librarian import Librarian
from hkos.services.project_manager import ProjectManager
from hkos.snapshot import SnapshotEngine
from hkos.storage import StorageEngine


@dataclass
class McpContext:
    """Wired HKOS services available to MCP tools (thin read facade)."""

    data_root: str
    profile: str
    cfg: ConfigLoader
    repos: RepositoryManager
    projects: ProjectManager
    campaigns: CampaignManager
    librarian: Librarian
    index: IndexEngine
    qc: IndexQueryExecutor
    retrieval: RetrievalEngine
    snapshots: SnapshotEngine
    doctor: HkosDoctor
    snapshot_persistence: FileSnapshotPersistence


def build_context(data_root: str, profile: str) -> McpContext:
    """Compose the HKOS services for one data root (documented wiring)."""
    cfg = ConfigLoader(profile=profile)
    cfg.load()
    engine = StorageEngine(
        root=data_root, config=cfg, logger=HKOSLogger(), version=VersionManager()
    )
    engine.initialize()
    repos = RepositoryManager(engine)
    projects = ProjectManager(repos, HKOSLogger())
    campaigns = CampaignManager(repos, HKOSLogger())
    librarian = Librarian(repos, HKOSLogger())
    store = IndexStore(engine)
    cache = IndexCache()
    index = IndexEngine(repos, store, HKOSLogger(), cache=cache)
    qc = IndexQueryExecutor(store, cache=cache)
    retrieval = RetrievalEngine(repos, qc, cfg, HKOSLogger())
    persistence = FileSnapshotPersistence(data_root)
    snapshots = SnapshotEngine(
        repos, persistence, HKOSLogger(), index_provider=qc.snapshot,
    )
    doctor = HkosDoctor(repos, index, snapshots, store)
    return McpContext(
        data_root=data_root,
        profile=profile,
        cfg=cfg,
        repos=repos,
        projects=projects,
        campaigns=campaigns,
        librarian=librarian,
        index=index,
        qc=qc,
        retrieval=retrieval,
        snapshots=snapshots,
        doctor=doctor,
        snapshot_persistence=persistence,
    )

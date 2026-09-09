"""HKOS demo: «Git для памяти ИИ-агентов» (DS-017 ЭТАП 6).

Сценарий: агент без HKOS повторяет прошлую ошибку; агент с HKOS запрашивает
память и получает в выдаче запись FAILURE (negative knowledge — first-class
результат) и связанное решение, избегая повтора. Zero LLM: никаких моделей —
детерминированная retrieve-выборка по индексу.
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
from hkos.services.librarian import Librarian
from hkos.services.project_manager import ProjectManager
from hkos.storage import StorageEngine


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="hkos-demo-failure-"))
    print(f"data root: {root}")
    cfg = ConfigLoader(); cfg.load()
    engine = StorageEngine(root=str(root), config=cfg, logger=HKOSLogger(), version=VersionManager())
    engine.initialize()
    repos = RepositoryManager(engine)
    projects = ProjectManager(repos, HKOSLogger())
    librarian = Librarian(repos, HKOSLogger())
    project = projects.create(name="TunnelOps", description="failure-recovery demo", tags=["demo"])
    memory = [
        Knowledge(title="mtu tunnel: UDP breaks above 1400 bytes", body="observed: UDP over tunnel dies when MTU > 1400; tcp survived, udp did not", kind="negative", tags=["mtu", "tunnel", "udp"]),
        Knowledge(title="Decision: clamp MSS to 1360 for tunnel UDP", body="set tcp mss 1360 on the tunnel; keeps UDP under the limit", tags=["mtu", "tunnel", "udp"]),
        Knowledge(title="mtu 1400 works over plain tcp", body="no tunnel involved; mtu 1400 fine on the lan", tags=["mtu", "tcp"]),
    ]
    ids = [librarian.register(project.id, k).id for k in memory]
    for k_id in ids:
        librarian.verify(project.id, k_id)
        librarian.canonicalize(project.id, k_id)
    store = IndexStore(engine); cache = IndexCache()
    index = IndexEngine(repos, store, HKOSLogger(), cache=cache); index.build(project.id)
    retrieval = RetrievalEngine(repos, IndexQueryExecutor(store, cache=cache), cfg, HKOSLogger())
    result = retrieval.retrieve("mtu tunnel", project_id=project.id, top_n=5)
    assert result.items
    first = result.items[0].entity
    assert first.category == "FAILURE"
    assert "Failure Priority" in result.items[0].explanation.reason
    print("OK: deterministic memory beats repetition (no LLM involved)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

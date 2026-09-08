"""HKOS demo: «Git для памяти ИИ-агентов» (DS-017 ЭТАП 6).

Сценарий: агент без HKOS повторяет прошлую ошибку; агент с HKOS запрашивает
память и получает в выдаче запись FAILURE (negative knowledge — first-class
результат) и связанное решение, избегая повтора. Zero LLM: никаких моделей —
детерминированная retrieve-выборка по индексу.

Usage (from the repository root):
    python examples/demo_failure_recovery.py

Всё живёт во временном data root; реальные данные не трогаются.
Exit: 0 — демо прошло (FAILURE найден первым).
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

    cfg = ConfigLoader()
    cfg.load()
    engine = StorageEngine(
        root=str(root), config=cfg, logger=HKOSLogger(),
        version=VersionManager())
    engine.initialize()
    repos = RepositoryManager(engine)
    projects = ProjectManager(repos, HKOSLogger())
    librarian = Librarian(repos, HKOSLogger())

    project = projects.create(
        name="TunnelOps", description="failure-recovery demo", tags=["demo"])
    print(f"project: {project.id}")

    # 1) Память: прошлый СБОЙ + принятое РЕШЕНИЕ (+ отвлекающий факт).
    memory = [
        Knowledge(  # FAILURE: kind=negative -> категория FAILURE
            title="mtu tunnel: UDP breaks above 1400 bytes",
            body="observed: UDP over tunnel dies when MTU > 1400; "
                 "tcp survived, udp did not",
            kind="negative",
            tags=["mtu", "tunnel", "udp"],
        ),
        Knowledge(  # DECISION: маркер 'decision' в title
            title="Decision: clamp MSS to 1360 for tunnel UDP",
            body="set tcp mss 1360 on the tunnel; keeps UDP under the limit",
            tags=["mtu", "tunnel", "udp"],
        ),
        Knowledge(  # FACT-путаница: тот же токен, не решение проблемы
            title="mtu 1400 works over plain tcp",
            body="no tunnel involved; mtu 1400 fine on the lan",
            tags=["mtu", "tcp"],
        ),
    ]
    ids = [librarian.register(project.id, k).id for k in memory]
    for k_id in ids:
        librarian.canonicalize(project.id, k_id)
    print(f"memory: {len(ids)} items saved (FAILURE + DECISION + FACT)")

    # 2) Индекс и retrieval.
    store = IndexStore(engine)
    cache = IndexCache()
    index = IndexEngine(repos, store, HKOSLogger(), cache=cache)
    index.build(project.id)
    qc = IndexQueryExecutor(store, cache=cache)
    retrieval = RetrievalEngine(repos, qc, cfg, HKOSLogger())

    # 3) Агент A (без HKOS): повторяет прежний ошибочный подход.
    print("\n--- agent A: no memory ---")
    print("A: 'I will set MTU 1400 on the tunnel again.'")
    print("A: '...UDP is dead again. Same failure as last week.'")

    # 4) Агент B (с HKOS): retrieve перед действием.
    print("\n--- agent B: consults HKOS ---")
    result = retrieval.retrieve("mtu tunnel", project_id=project.id, top_n=5)
    print(f"B: retrieve('mtu tunnel') -> {len(result.items)} item(s):")
    for item in result.items:
        print(f"   [{item.entity.category}] {item.entity.title}")
    assert result.items, "retrieval returned nothing"
    first = result.items[0].entity
    assert first.category == "FAILURE", (
        f"expected FAILURE first (Failure Priority factor), got "
        f"{first.category}")
    assert "Failure Priority" in result.items[0].explanation.reason
    print(f"B: top hit is the FAILURE record ({first.title}) — do not repeat.")
    print("B: applying the recorded decision: clamp MSS to 1360.")
    print("B: UDP survives. Outcome recorded.")

    print("\nOK: deterministic memory beats repetition (no LLM involved)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Hermes Production Hooks (DS-016 ЭТАП 2)."""
from hkos.index import IndexEngine
from hkos.integration.hermes.agent_lock import LOCK_MODE_WRITE, AgentLock
from hkos.performance.context_profiles import PerformanceContextOptimizer
from hkos.repository.models import Knowledge
from hkos.services.librarian import Librarian
from hkos.services.memory_service import MemoryService
from hkos.snapshot import SnapshotEngine
__all__ = ["HermesProductionHooks"]

class HermesProductionHooks:
    def __init__(self, memory: MemoryService, librarian: Librarian, index: IndexEngine, snapshots: SnapshotEngine, optimizer: PerformanceContextOptimizer | None = None, lock: AgentLock | None = None) -> None:
        self._memory = memory; self._librarian = librarian; self._index = index; self._snapshots = snapshots; self._optimizer = optimizer or PerformanceContextOptimizer("NORMAL"); self._lock = lock

    def startup(self) -> dict[str, object]:
        project_ids = [p.id for p in self._memory._projects.list()]
        for project_id in project_ids[:1]: self._index.statistics(project_id)
        return {"ready": True, "repository_available": True, "index_available": True, "projects": len(project_ids)}

    def retrieve_before_task(self, agent_id: str, query: str, project_name: str = "", project_id: str = "", campaign_id: str = "", goal: str = "") -> dict[str, object]:
        if hasattr(self._memory, "reset_fallbacks"): self._memory.reset_fallbacks()
        if self._lock is not None: self._lock.acquire(LOCK_MODE_WRITE)
        try: prepared = self._memory.prepare_context(agent_id, query, project_name, project_id, campaign_id, goal)
        finally:
            if self._lock is not None: self._lock.release(LOCK_MODE_WRITE)
        context = prepared.context; optimized = context; tokens_before = 0; tokens_after = 0
        if context is not None:
            tokens_before = self._estimate_tokens(context); optimized = self._optimizer.compress(context); tokens_after = self._estimate_tokens(optimized)
        return {"project_id": prepared.project_id, "campaign_id": prepared.campaign_id, "snapshot_used": prepared.snapshot_used, "retrieval_items": prepared.retrieval_items, "context": context, "optimized": optimized, "tokens_before": tokens_before, "tokens_after": tokens_after, "reduction": ((tokens_before - tokens_after) / tokens_before if tokens_before else 0.0)}

    def save_after_task(self, agent_id: str, project_id: str, knowledge: list[Knowledge] | None = None, failures: list[Knowledge] | None = None, update_snapshot: bool = True) -> dict[str, object]:
        if self._lock is not None: self._lock.acquire(LOCK_MODE_WRITE)
        try:
            result = self._memory.save_results(agent_id, project_id, knowledge=knowledge, failures=failures, update_snapshot=False)
            all_ids = list(result.saved) + list(result.failures)
            for knowledge_id in all_ids:
                self._librarian.verify(project_id, knowledge_id)
                self._librarian.canonicalize(project_id, knowledge_id)
                self._index.update(project_id, knowledge_id, "knowledge")
            if update_snapshot: self._snapshots.create(project_id, reason="hermes-save", force=True)
            return {"saved": result.saved, "failures": result.failures, "canonicalized": len(all_ids), "snapshot_updated": update_snapshot}
        finally:
            if self._lock is not None: self._lock.release(LOCK_MODE_WRITE)

    @staticmethod
    def _estimate_tokens(context: object) -> int:
        items = getattr(context, "items", None)
        if isinstance(items, list): return sum(len(str(getattr(getattr(i, "entity", i), "body", ""))) for i in items)
        sections = getattr(context, "sections", {})
        return sum(len(str(getattr(getattr(i, "entity", i), "body", ""))) for section in sections.values() for i in section)

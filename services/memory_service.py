"""HKOS Memory Service (DS-012 ЭТАП 5).

============================================
Оркестратор полного жизненного цикла задачи Hermes (HKOS-06:
Memory Manager). ТОЛЬКО оркестрация поверх публичных интерфейсов:
ProjectManager, CampaignManager, RetrievalEngine, ContextBuilder,
Librarian, IndexEngine, SnapshotEngine.

Правила:
- НЕ обходит Librarian (знания пишутся только через него);
- НЕ создаёт второй Repository; Snapshot НЕ источник истины;
- graceful degradation (retrieval/snapshot/librarian) без потери данных;
- идентичность агента — параметром (agent_id), без зависимостей от
  интеграционного слоя (services не импортируют integration).

Pipeline:
    resolve_project -> resolve_campaign -> prepare_context
        (snapshot -> retrieval -> context) -> save_results
        (librarian.register -> index.update -> snapshot.create)
"""

from dataclasses import dataclass, field
from typing import Final

from hkos.context.context_builder import ContextBuilder
from hkos.core.logger import HKOSLogger
from hkos.index.index_engine import IndexEngine
from hkos.repository.models import Campaign, Knowledge
from hkos.retrieval.retrieval_engine import RetrievalEngine
from hkos.services.campaign_manager import CampaignManager
from hkos.services.librarian.librarian import Librarian
from hkos.services.project_manager import ProjectInfo, ProjectManager
from hkos.snapshot.snapshot_engine import SnapshotEngine

__all__ = ["MemoryService", "PreparedContext", "SaveResult"]

CATEGORY_FAILURE: Final[str] = "FAILURE"


@dataclass(frozen=True)
class PreparedContext:
    """Результат prepare_context (данные между слоями)."""

    project_id: str
    campaign_id: str
    snapshot_used: bool
    retrieval_items: list[object] = field(default_factory=list)
    context: object | None = None


@dataclass(frozen=True)
class SaveResult:
    """Результат save_results."""

    saved: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    pending: int = 0


class MemoryService:
    """Оркестратор памяти для жизненного цикла задачи Hermes."""

    def __init__(
        self,
        projects: ProjectManager,
        campaigns: CampaignManager,
        retrieval: RetrievalEngine,
        context_builder: ContextBuilder,
        librarian: Librarian,
        index: IndexEngine,
        snapshots: SnapshotEngine,
        logger: HKOSLogger | None = None,
    ) -> None:
        """Инициализация (dependency injection публичных фасадов)."""
        self._projects = projects
        self._campaigns = campaigns
        self._retrieval = retrieval
        self._context_builder = context_builder
        self._librarian = librarian
        self._index = index
        self._snapshots = snapshots
        self._logger = logger or HKOSLogger()
        self._pending_knowledge: list[Knowledge] = []
        self._snapshot_available = True
        self._retrieval_available = True
        self._librarian_available = True

    # ---- Project Resolver (DS-012 ЭТАП 5 §3) ----

    def resolve_project(
        self, project_name: str = "", project_id: str = ""
    ) -> ProjectInfo:
        """Определить проект: по id, по имени (существующий), иначе создать.

        Raises:
            RuntimeError: ни id, ни имя не заданы.

        """
        if project_id:
            return self._projects.info(project_id)
        if project_name:
            for candidate in self._projects.list():
                if candidate.name == project_name:
                    return candidate
            created = self._projects.create(name=project_name)
            return self._projects.info(created.id)
        raise RuntimeError("resolve_project requires project_id or project_name")

    # ---- Campaign Resolver (DS-012 ЭТАП 5 §3) ----

    def resolve_campaign(
        self, project_id: str, campaign_id: str = "", goal: str = ""
    ) -> Campaign:
        """Определить кампанию: заданную (продолжение), активную, иначе создать новую.

        Кампания БЕЗ проекта запрещена.

        Raises:
            RuntimeError: project_id пуст (campaign without project).

        """
        if not project_id:
            raise RuntimeError("campaign without project is forbidden")
        if campaign_id:
            for campaign in self._campaigns.list(project_id):
                if campaign.id == campaign_id:
                    return campaign
            raise RuntimeError(f"campaign not found: {campaign_id}")
        return self.get_or_create_campaign(project_id, goal)

    def _find_active_campaign(self, project_id: str) -> Campaign | None:
        """Активная (RUNNING) кампания проекта (или None)."""
        for campaign in self._campaigns.list(project_id):
            if campaign.status == "RUNNING":
                return campaign
        return None

    def get_or_create_campaign(
        self, project_id: str, goal: str = ""
    ) -> Campaign:
        """Найти пригодную кампанию проекта или создать новую (get_or_create).

        Порядок (DS-017 campaign lifecycle consistency):

        1. активная RUNNING-кампания -> reuse (продолжение контекста);
        2. кампания с тем же нормализованным goal (CREATED/READY/RUNNING)
           -> reuse (защита от duplicate campaigns);
        3. иначе создать новую (CREATED) и синхронизировать Index
           (фикс incident 001: resolve_campaign не обновлял проекцию).

        Raises:
            RuntimeError: project_id пуст (campaign without project).

        """
        if not project_id:
            raise RuntimeError("campaign without project is forbidden")
        active = self._find_active_campaign(project_id)
        if active is not None:
            return active
        normalized = goal.strip().lower()
        if normalized:
            for campaign in self._campaigns.list(project_id):
                if (
                    campaign.status in ("CREATED", "READY", "RUNNING")
                    and campaign.goal.strip().lower() == normalized
                ):
                    return campaign
        created = self._campaigns.create(
            project_id=project_id, goal=goal or "task")
        # Incident 001: кампания обязана попасть в Index (Repository == Index).
        # Сбой индекса (производное) НЕ роняет retrieve-путь (graceful
        # degradation DS-012): warning + рассинхронизация видна doctor'ом.
        try:
            self._index.update(project_id, created.id, "campaign")
        except Exception as exc:  # noqa: BLE001 - индекс производное
            self._logger.warning(
                f"MemoryService: index update failed for campaign "
                f"{created.id} ({exc}); doctor will report desync")
        return created

    # ---- Prepare Context (DS-012 ЭТАП 5 §2) ----

    def prepare_context(
        self,
        agent_id: str,
        query: str,
        project_name: str = "",
        project_id: str = "",
        campaign_id: str = "",
        goal: str = "",
    ) -> PreparedContext:
        """Подготовить контекст задачи (project -> campaign -> контекст).

        Snapshot (если есть) -> retrieval -> context; graceful degradation
        при недоступности.
        """
        project = self.resolve_project(project_name, project_id)
        campaign = self.resolve_campaign(project.id, campaign_id, goal)
        snapshot_used = False
        snapshot = None
        if self._snapshot_available:
            try:
                snapshot = self._snapshots.load(project.id)
                snapshot_used = snapshot is not None
            except Exception:
                self._snapshot_available = False
                self._logger.warning("MemoryService: snapshot unavailable (fallback)")
        items: list[object] = []
        result = None
        if self._retrieval_available:
            try:
                result = self._retrieval.retrieve(query, project_id=project.id)
                items = list(result.items)
            except Exception:
                self._retrieval_available = False
                self._logger.warning("MemoryService: retrieval unavailable (fallback)")
        context = None
        if result is not None:
            try:
                context = self._context_builder.build(result, project.id)
            except Exception:
                self._logger.warning("MemoryService: context build failed")
        return PreparedContext(
            project_id=project.id,
            campaign_id=campaign.id,
            snapshot_used=snapshot_used,
            retrieval_items=items,
            context=context,
        )

    # ---- Save Results (DS-012 ЭТАП 5 §2) ----

    def save_results(
        self,
        agent_id: str,
        project_id: str,
        knowledge: list[Knowledge] | None = None,
        failures: list[Knowledge] | None = None,
        update_snapshot: bool = True,
    ) -> SaveResult:
        """Сохранить результаты задачи (knowledge + failures).

        Через Librarian, index.update, snapshot.create при необходимости.
        """
        saved: list[str] = []
        failure_ids: list[str] = []
        for item in (knowledge or []):
            entity = self._save_knowledge(project_id, item)
            if entity is not None:
                saved.append(entity.id)
        for item in (failures or []):
            entity = self._save_knowledge(project_id, item)
            if entity is not None:
                failure_ids.append(entity.id)
        if self._librarian_available:
            for entity_id in saved + failure_ids:
                self._index.update(project_id, entity_id, "knowledge")
            if update_snapshot and self._snapshot_available:
                try:
                    self._snapshots.create(
                        project_id, reason="task_completed",
                        author=agent_id, force=False,
                    )
                except Exception:
                    self._logger.warning("MemoryService: snapshot create skipped")
        return SaveResult(
            saved=saved,
            failures=failure_ids,
            pending=len(self._pending_knowledge),
        )

    def _save_knowledge(
        self, project_id: str, item: Knowledge
    ) -> Knowledge | None:
        """Запись через Librarian; при недоступности — pending queue."""
        if not self._librarian_available:
            self._pending_knowledge.append(item)
            return None
        try:
            return self._librarian.register(project_id, item)
        except Exception:
            self._librarian_available = False
            self._pending_knowledge.append(item)
            self._logger.warning("MemoryService: librarian unavailable; queued")
            return None

    # ---- Восстановление после сбоя (DS-012 ЭТАП 5 §8) ----

    def drain_pending(self) -> int:
        """После восстановления Librarian: повторная запись очереди."""
        drained = self._pending_knowledge
        self._pending_knowledge = []
        self._librarian_available = True
        return len(drained)

    def pending_count(self) -> int:
        """Число знаний в очереди ожидания (librarian unavailable)."""
        return len(self._pending_knowledge)

    def reset_fallbacks(self) -> None:
        """Сброс флагов недоступности (после восстановления)."""
        self._retrieval_available = True
        self._snapshot_available = True
        self._librarian_available = True

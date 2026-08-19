"""HKOS Campaign Manager (DS-005 §5-6, IP-005 Stage 7)
===================================================
CampaignManager — оркестратор жизненного цикла кампаний.

Работает ТОЛЬКО через RepositoryManager.campaigns; прямой доступ
к Storage Engine запрещён (IP-005 §4, §10).

Оркестрация: Factory (создание), Validator (проверка),
Statistics/Progress (вычисление), State Machine (переходы),
Repository (хранение). Собственных алгоритмов создания, проверки
и расчётов менеджер не содержит.

Публичный API (ровно эти методы, без дополнительных):
    create, open, pause, resume, close, archive, delete,
    status, progress, statistics, list, validate
"""

from datetime import datetime, timezone

from hkos.core.logger import HKOSLogger
from hkos.repository.campaign_repository import CampaignRepository
from hkos.repository.exceptions import RepositoryNotFoundError
from hkos.repository.models import Campaign, CampaignStep, JournalEntry
from hkos.repository.repository_manager import RepositoryManager
from hkos.services.campaign_factory import CampaignFactory
from hkos.services.campaign_state import (
    CAMPAIGN_STATE_ARCHIVED,
    CAMPAIGN_STATE_COMPLETED,
    CAMPAIGN_STATE_CREATED,
    CAMPAIGN_STATE_FAILED,
    CAMPAIGN_STATE_PAUSED,
    CAMPAIGN_STATE_READY,
    CAMPAIGN_STATE_RUNNING,
    CAMPAIGN_STATE_WAITING_EXTERNAL,
    CampaignState,
)
from hkos.services.campaign_statistics import (
    CampaignStatistics,
    CampaignStatisticsResult,
)
from hkos.services.campaign_validator import CampaignValidator
from hkos.services.exceptions import (
    CampaignNotFoundError,
    CampaignStateError,
)
from hkos.services.project_validator import ValidationResult

__all__ = ["CampaignManager", "CampaignStatus"]

# События Journal (IP-005 §13).
EVENT_CREATED: str = "Campaign Created"
EVENT_READY: str = "Campaign Ready"
EVENT_RUNNING: str = "Campaign Running"
EVENT_PAUSED: str = "Campaign Paused"
EVENT_RESUMED: str = "Campaign Resumed"
EVENT_WAITING_EXTERNAL: str = "Campaign Waiting External"
EVENT_FAILED: str = "Campaign Failed"
EVENT_COMPLETED: str = "Campaign Completed"
EVENT_ARCHIVED: str = "Campaign Archived"


def _now_iso() -> str:
    """Текущее время ISO-8601 (UTC, микросекунды)."""
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


class CampaignStatus:
    """Статус кампании (результат status())."""

    def __init__(
        self,
        campaign_id: str,
        project: str,
        state: str,
        updated_at: str,
    ) -> None:
        """Инициализация статуса."""
        self.campaign_id = campaign_id
        self.project = project
        self.state = state
        self.updated_at = updated_at

    def as_dict(self) -> dict[str, str]:
        """Статус как словарь."""
        return {
            "campaign_id": self.campaign_id,
            "project": self.project,
            "state": self.state,
            "updated_at": self.updated_at,
        }


class CampaignManager:
    """Оркестратор жизненного цикла кампаний (единственный orchestrator)."""

    # Состояния, из которых допустим переход в FAILED (IP-005 §8).
    _FAILABLE_STATES: frozenset[str] = frozenset({
        CAMPAIGN_STATE_READY,
        CAMPAIGN_STATE_RUNNING,
        CAMPAIGN_STATE_PAUSED,
        CAMPAIGN_STATE_WAITING_EXTERNAL,
    })

    def __init__(
        self,
        repositories: RepositoryManager,
        logger: HKOSLogger,
        factory: CampaignFactory | None = None,
        validator: CampaignValidator | None = None,
    ) -> None:
        """Инициализация Campaign Manager.

        Args:
            repositories: RepositoryManager (Sprint 3) — доступ через .campaigns.
            logger: HKOSLogger (Sprint 1) — системное журналирование.
            factory: CampaignFactory; создаётся по умолчанию.
            validator: CampaignValidator; создаётся по умолчанию.
        """
        self._repositories = repositories
        self._campaigns: CampaignRepository = repositories.campaigns
        self._logger = logger
        self._factory = factory if factory is not None else CampaignFactory(
            self._campaigns
        )
        self._validator = (
            validator if validator is not None else CampaignValidator(self._campaigns)
        )

    # --- Внутренние операции (private, IP-005 §7) ---

    def _load(self, project_id: str, campaign_id: str) -> Campaign:
        """Загрузить кампанию или поднять CampaignNotFoundError."""
        try:
            return self._campaigns.load(project_id, campaign_id)
        except RepositoryNotFoundError as e:
            raise CampaignNotFoundError(
                f"Campaign not found: {campaign_id} in project {project_id}"
            ) from e

    def _save(self, campaign: Campaign) -> Campaign:
        """Сохранить кампанию."""
        return self._campaigns.update(campaign)

    def _append_journal(
        self,
        campaign: Campaign,
        event: str,
        details: str = "",
    ) -> Campaign:
        """Добавить запись в Journal (append-only, IP-005 §13).

        Удаление и изменение существующих записей запрещено —
        публичного API для этого не существует.
        """
        campaign.journal.append(
            JournalEntry(
                timestamp=_now_iso(),
                campaign_id=campaign.id,
                event=event,
                details=details,
            )
        )
        return campaign

    def _transition(
        self,
        campaign: Campaign,
        target: str,
        event: str,
        details: str = "",
    ) -> Campaign:
        """Применить переход через CampaignState и записать событие."""
        state = CampaignState(campaign.status)
        state.transition_to(target)
        campaign.status = state.current
        self._append_journal(campaign, event, details)
        return self._save(campaign)

    def _log(self, message: str) -> None:
        """Системный журнал (отдельно от Journal кампании)."""
        self._logger.info(message)

    # --- Публичный API (ровно 12 методов) ---

    def create(
        self,
        project_id: str,
        goal: str,
        steps: list[CampaignStep] | None = None,
    ) -> Campaign:
        """Создать кампанию (CREATED) через CampaignFactory.

        Raises:
            CampaignError: Если фабрика не может сохранить кампанию.
        """
        campaign = self._factory.create(
            project_id=project_id,
            goal=goal,
            steps=steps,
            timestamp=_now_iso(),
        )
        self._log(f"Campaign Created: {campaign.id} in project {project_id}")
        return campaign

    def open(self, project_id: str, campaign_id: str) -> Campaign:
        """Открыть кампанию: CREATED -> READY, затем READY -> RUNNING.

        Первый вызов переводит кампанию в READY, повторный — в RUNNING
        (семантика продвижения, задокументирована в отчёте DS-005).
        """
        campaign = self._load(project_id, campaign_id)
        if campaign.status == CAMPAIGN_STATE_CREATED:
            result = self._transition(
                campaign, CAMPAIGN_STATE_READY, EVENT_READY
            )
            self._log(f"Campaign Opened: {campaign_id}")
            return result
        if campaign.status == CAMPAIGN_STATE_READY:
            result = self._transition(
                campaign, CAMPAIGN_STATE_RUNNING, EVENT_RUNNING
            )
            self._log(f"Campaign Running: {campaign_id}")
            return result
        raise CampaignStateError(
            f"open() is not allowed from state {campaign.status}"
        )

    def pause(self, project_id: str, campaign_id: str) -> Campaign:
        """Поставить кампанию на паузу (RUNNING -> PAUSED)."""
        campaign = self._load(project_id, campaign_id)
        result = self._transition(campaign, CAMPAIGN_STATE_PAUSED, EVENT_PAUSED)
        self._log(f"Campaign Paused: {campaign_id}")
        return result

    def resume(self, project_id: str, campaign_id: str) -> Campaign:
        """Возобновить кампанию (PAUSED|WAITING_EXTERNAL -> RUNNING)."""
        campaign = self._load(project_id, campaign_id)
        result = self._transition(campaign, CAMPAIGN_STATE_RUNNING, EVENT_RESUMED)
        self._log(f"Campaign Resumed: {campaign_id}")
        return result

    def close(self, project_id: str, campaign_id: str) -> Campaign:
        """Завершить кампанию (RUNNING -> COMPLETED)."""
        campaign = self._load(project_id, campaign_id)
        result = self._transition(
            campaign, CAMPAIGN_STATE_COMPLETED, EVENT_COMPLETED
        )
        self._log(f"Campaign Completed: {campaign_id}")
        return result

    def archive(self, project_id: str, campaign_id: str) -> Campaign:
        """Архивировать кампанию (COMPLETED|FAILED -> ARCHIVED)."""
        campaign = self._load(project_id, campaign_id)
        result = self._transition(
            campaign, CAMPAIGN_STATE_ARCHIVED, EVENT_ARCHIVED
        )
        self._log(f"Campaign Archived: {campaign_id}")
        return result

    def delete(self, project_id: str, campaign_id: str) -> None:
        """Удалить кампанию (документ campaign.json).

        Raises:
            CampaignNotFoundError: Если кампания отсутствует.
        """
        if not self._campaigns.exists(project_id, campaign_id):
            raise CampaignNotFoundError(
                f"Campaign not found: {campaign_id} in project {project_id}"
            )
        self._campaigns.delete(project_id, campaign_id)
        self._log(f"Campaign Deleted: {campaign_id}")

    def status(self, project_id: str, campaign_id: str) -> CampaignStatus:
        """Статус кампании (состояние + метаданные)."""
        campaign = self._load(project_id, campaign_id)
        return CampaignStatus(
            campaign_id=campaign.id,
            project=campaign.project,
            state=campaign.status,
            updated_at=campaign.updated_at,
        )

    def progress(self, project_id: str, campaign_id: str) -> int:
        """Прогресс кампании (0..100), вычисляется из этапов.

        Progress никогда не хранится и не задаётся вручную (IP-005 §11).
        """
        campaign = self._load(project_id, campaign_id)
        return CampaignStatistics.calculate_progress(campaign.steps)

    def statistics(
        self, project_id: str, campaign_id: str
    ) -> CampaignStatisticsResult:
        """Статистика кампании (все значения производные)."""
        campaign = self._load(project_id, campaign_id)
        return CampaignStatistics.calculate(campaign)

    def list(self, project_id: str) -> list[Campaign]:
        """Список кампаний проекта."""
        return self._campaigns.list(project_id)

    def validate(self, project_id: str, campaign_id: str) -> ValidationResult:
        """Проверить кампанию (валидатор не изменяет Repository)."""
        result = self._validator.validate(project_id, campaign_id)
        if not result.valid:
            self._logger.warning(
                f"Validation Failed: {campaign_id}: {result.errors}"
            )
        return result

    # --- Приватные хуки оркестрации (IP-005 §7) ---

    def _wait_external(
        self, project_id: str, campaign_id: str, details: str = ""
    ) -> Campaign:
        """Перевести кампанию в ожидание внешних данных (RUNNING).

        Публичного метода для этого перехода в API DS-005 нет;
        хук используется внутренними компонентами и тестами.
        """
        campaign = self._load(project_id, campaign_id)
        result = self._transition(
            campaign, CAMPAIGN_STATE_WAITING_EXTERNAL, EVENT_WAITING_EXTERNAL,
            details,
        )
        self._log(f"Campaign Waiting External: {campaign_id}")
        return result

    def _fail(
        self, project_id: str, campaign_id: str, details: str = ""
    ) -> Campaign:
        """Перевести кампанию в FAILED (READY|RUNNING|PAUSED|WAITING_EXTERNAL).

        Публичного метода для этого перехода в API DS-005 нет;
        хук используется внутренними компонентами и тестами.
        """
        campaign = self._load(project_id, campaign_id)
        if campaign.status not in self._FAILABLE_STATES:
            raise CampaignStateError(
                f"FAILED is not allowed from state {campaign.status}"
            )
        result = self._transition(
            campaign, CAMPAIGN_STATE_FAILED, EVENT_FAILED, details
        )
        self._log(f"Campaign Failed: {campaign_id}")
        return result

    def _update_step(
        self,
        project_id: str,
        campaign_id: str,
        step_id: str,
        status: str,
        retries: int | None = None,
    ) -> Campaign:
        """Обновить статус этапа (источник истины Progress).

        Приватный хук: публичный API DS-005 не включает регистрацию
        этапов; статусы этапов изменяются внутренними компонентами.
        """
        campaign = self._load(project_id, campaign_id)
        for step in campaign.steps:
            if step.id == step_id:
                step.status = status
                if retries is not None:
                    step.retries = retries
                return self._save(campaign)
        raise CampaignNotFoundError(
            f"Step not found: {step_id} in campaign {campaign_id}"
        )

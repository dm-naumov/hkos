"""HKOS Campaign Service (IP-005 §3.1)
====================================
CampaignService — исключительно фасад над CampaignManager.

Намеренно не содержит бизнес-логики и вычислений: все вызовы
делегируются Manager 1:1. Создан заранее как стабильная граница
для будущего DI/Registry (DS-012).
"""

from hkos.core.logger import HKOSLogger
from hkos.repository.models import Campaign, CampaignStep
from hkos.services.campaign_manager import CampaignManager, CampaignStatus
from hkos.services.campaign_statistics import CampaignStatisticsResult
from hkos.services.project_validator import ValidationResult

__all__ = ["CampaignService"]


class CampaignService:
    """Тонкий фасад сервисного слоя кампаний (без логики)."""

    def __init__(self, manager: CampaignManager, logger: HKOSLogger) -> None:
        """Инициализация сервиса.

        Args:
            manager: CampaignManager (единственный источник операций).
            logger: HKOSLogger.
        """
        self._manager = manager
        self._logger = logger

    @property
    def manager(self) -> CampaignManager:
        """Внутренний CampaignManager."""
        return self._manager

    def create(
        self,
        project_id: str,
        goal: str,
        steps: list[CampaignStep] | None = None,
    ) -> Campaign:
        """Создать кампанию (делегирование)."""
        return self._manager.create(project_id, goal, steps)

    def open(self, project_id: str, campaign_id: str) -> Campaign:
        """Открыть кампанию (делегирование)."""
        return self._manager.open(project_id, campaign_id)

    def pause(self, project_id: str, campaign_id: str) -> Campaign:
        """Поставить на паузу (делегирование)."""
        return self._manager.pause(project_id, campaign_id)

    def resume(self, project_id: str, campaign_id: str) -> Campaign:
        """Возобновить (делегирование)."""
        return self._manager.resume(project_id, campaign_id)

    def close(self, project_id: str, campaign_id: str) -> Campaign:
        """Завершить (делегирование)."""
        return self._manager.close(project_id, campaign_id)

    def archive(self, project_id: str, campaign_id: str) -> Campaign:
        """Архивировать (делегирование)."""
        return self._manager.archive(project_id, campaign_id)

    def delete(self, project_id: str, campaign_id: str) -> None:
        """Удалить (делегирование)."""
        self._manager.delete(project_id, campaign_id)

    def status(self, project_id: str, campaign_id: str) -> CampaignStatus:
        """Статус (делегирование)."""
        return self._manager.status(project_id, campaign_id)

    def progress(self, project_id: str, campaign_id: str) -> int:
        """Прогресс (делегирование)."""
        return self._manager.progress(project_id, campaign_id)

    def statistics(
        self, project_id: str, campaign_id: str
    ) -> CampaignStatisticsResult:
        """Статистика (делегирование)."""
        return self._manager.statistics(project_id, campaign_id)

    def list(self, project_id: str) -> list[Campaign]:
        """Список кампаний (делегирование)."""
        return self._manager.list(project_id)

    def validate(self, project_id: str, campaign_id: str) -> ValidationResult:
        """Проверить кампанию (делегирование)."""
        return self._manager.validate(project_id, campaign_id)

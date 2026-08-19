"""HKOS Campaign Factory (DS-005 §7, IP-005 Stage 2)
================================================
CampaignFactory отвечает ИСКЛЮЧИТЕЛЬНО за создание Campaign:

- генерирует UUID;
- создаёт документ кампании (campaign.json через CampaignRepository);
- инициализирует обязательные разделы: state (status=CREATED),
  progress (steps), journal (запись "Campaign Created");
- заполняет обязательные поля (project, goal, schema_version).

Фабрике запрещено: открывать/архивировать Campaign, выполнять validate,
рассчитывать Progress/Statistics, изменять существующие Campaign.
Документы создаются через Repository Layer (IP-005, ARCHITECTURAL
COMMENTS §1); прямой доступ к Storage Engine запрещён.
"""

import uuid

from hkos.repository.campaign_repository import CampaignRepository
from hkos.repository.models import Campaign, CampaignStep, JournalEntry
from hkos.services.campaign_state import CAMPAIGN_STATE_CREATED

__all__ = ["CampaignFactory"]

# Версия схемы кампании (конверт HKOS-08).
CAMPAIGN_SCHEMA_VERSION: str = "1.0"

# Событие создания в Journal.
JOURNAL_EVENT_CREATED: str = "Campaign Created"


class CampaignFactory:
    """Фабрика создания кампаний (единственная обязанность — создание)."""

    def __init__(self, repository: CampaignRepository) -> None:
        """Инициализация фабрики.

        Args:
            repository: CampaignRepository из RepositoryManager.campaigns.
        """
        self._repository = repository

    def create(
        self,
        project_id: str,
        goal: str,
        steps: list[CampaignStep] | None = None,
        timestamp: str = "",
    ) -> Campaign:
        """Создать кампанию и сохранить через репозиторий.

        Args:
            project_id: UUID проекта-владельца (обязательное поле).
            goal: Цель кампании (обязательное поле).
            steps: Этапы кампании (источник истины Progress).
            timestamp: Метка времени ISO-8601 (для Journal).

        Returns:
            Сохранённая Campaign со статусом CREATED, инициализированными
            steps и journal (запись "Campaign Created").
        """
        campaign_id = str(uuid.uuid4())
        # Этапам без id назначаются UUID (обязательные ссылки, IP-005 §8).
        prepared_steps = [
            CampaignStep(
                id=step.id or str(uuid.uuid4()),
                title=step.title,
                status=step.status,
                retries=step.retries,
            )
            for step in (steps or [])
        ]
        journal = [
            JournalEntry(
                timestamp=timestamp,
                campaign_id=campaign_id,
                event=JOURNAL_EVENT_CREATED,
                details=f"Campaign {campaign_id} created in project {project_id}",
            )
        ]
        campaign = Campaign(
            id=campaign_id,
            project=project_id,
            goal=goal,
            status=CAMPAIGN_STATE_CREATED,
            schema_version=CAMPAIGN_SCHEMA_VERSION,
            steps=prepared_steps,
            journal=journal,
        )
        return self._repository.save(campaign)

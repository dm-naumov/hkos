"""HKOS Campaign Repository (DS-003 §8)
=====================================
Работа с Campaign, CampaignState и CampaignMetadata.
"""

from typing import Any

from hkos.repository.base_repository import BaseRepository
from hkos.repository.exceptions import RepositoryParseError
from hkos.repository.models import (
    CAMPAIGN_STATUS_ACTIVE,
    CAMPAIGN_STATUS_ARCHIVED,
    CAMPAIGN_STATUS_CLOSED,
    Campaign,
    CampaignMetadata,
    CampaignState,
    CampaignStep,
    JournalEntry,
)
from hkos.storage.path_manager import PathManager

__all__ = ["CampaignRepository"]


class CampaignRepository(BaseRepository[Campaign]):
    """Репозиторий кампаний проекта.

    Кампания адресуется парой (project, campaign_id); документ —
    projects/<p>/campaigns/<c>/campaign.json.
    """

    _type_name: str = "campaign"

    def _dir_path(self, project: str) -> str:
        """Каталог кампаний проекта: projects/<p>/campaigns."""
        return PathManager.campaigns(self._storage.root, project)

    def _file_path(self, project: str, object_id: str) -> str:
        """Путь документа кампании."""
        return PathManager.campaign_file(self._storage.root, project, object_id)

    def _to_data(self, entity: Campaign) -> dict[str, object]:
        """Раздел data документа (HKOS-08 §4)."""
        return {
            "id": entity.id,
            "project": entity.project,
            "goal": entity.goal,
            "status": entity.status,
            "cycles": entity.cycles,
            "snapshot": entity.snapshot,
            "worker_reports": entity.worker_reports,
            "boss_reports": entity.boss_reports,
            "artifacts": entity.artifacts,
            "schema_version": entity.schema_version,
            "steps": [step.to_dict() for step in entity.steps],
            "journal": [entry.to_dict() for entry in entity.journal],
        }

    def _from_data(self, doc: dict[str, Any]) -> Campaign:
        """Сущность из документа HKOS-08."""
        data = doc.get("data", {})
        if not isinstance(data, dict):
            raise RepositoryParseError("Campaign document has invalid 'data' section")
        steps_data = data.get("steps", [])
        if not isinstance(steps_data, list):
            raise RepositoryParseError(
                "Campaign document has invalid 'steps' section"
            )
        journal_data = data.get("journal", [])
        if not isinstance(journal_data, list):
            raise RepositoryParseError(
                "Campaign document has invalid 'journal' section"
            )
        steps = [
            CampaignStep.from_dict(item)
            for item in steps_data
            if isinstance(item, dict)
        ]
        journal = [
            JournalEntry.from_dict(item)
            for item in journal_data
            if isinstance(item, dict)
        ]
        return Campaign(
            id=data.get("id", ""),
            project=data.get("project", ""),
            goal=data.get("goal", ""),
            status=data.get("status", CAMPAIGN_STATUS_ACTIVE),
            cycles=data.get("cycles", 0),
            snapshot=data.get("snapshot", ""),
            worker_reports=data.get("worker_reports", []),
            boss_reports=data.get("boss_reports", []),
            artifacts=data.get("artifacts", []),
            schema_version=data.get("schema_version", "1.0"),
            steps=steps,
            journal=journal,
            created_at=doc.get("created_at", ""),
            updated_at=doc.get("updated_at", ""),
        )

    def _list_ids(self, project: str) -> list[str]:
        """Id кампаний: каталоги в campaigns/, содержащие campaign.json."""
        campaigns_dir = PathManager.campaigns(self._storage.root, project)
        if not self._storage.exists(campaigns_dir):
            return []
        return [
            name
            for name in self._storage.list(campaigns_dir)
            if self._storage.exists(
                PathManager.campaign_file(self._storage.root, project, name)
            )
        ]

    def create_campaign(self, campaign: Campaign) -> Campaign:
        """Создать кампанию (сохранить с назначением UUID при необходимости)."""
        return self.save(campaign)

    def load_campaign(self, project: str, campaign_id: str) -> Campaign:
        """Загрузить кампанию по проекту и id."""
        return self.load(project, campaign_id)

    def update_campaign(self, campaign: Campaign) -> Campaign:
        """Обновить кампанию."""
        return self.update(campaign)

    def _set_status(
        self, project: str, campaign_id: str, status: str
    ) -> CampaignState:
        """Установить статус кампании (явная команда вызывающего компонента)."""
        campaign = self.load(project, campaign_id)
        campaign.status = status
        self.update(campaign)
        updated_at = self._read_doc(project, campaign_id).get(
            self._json.KEY_UPDATED_AT, ""
        )
        return CampaignState(status=campaign.status, updated_at=updated_at)

    def close_campaign(self, project: str, campaign_id: str) -> CampaignState:
        """Закрыть кампанию (статус closed)."""
        return self._set_status(project, campaign_id, CAMPAIGN_STATUS_CLOSED)

    def archive_campaign(self, project: str, campaign_id: str) -> CampaignState:
        """Архивировать кампанию (статус archived)."""
        return self._set_status(project, campaign_id, CAMPAIGN_STATUS_ARCHIVED)

    def load_metadata(self, project: str, campaign_id: str) -> CampaignMetadata:
        """Метаданные документа кампании (конверт HKOS-08)."""
        doc = self._read_doc(project, campaign_id)
        return CampaignMetadata(
            created_at=doc.get("created_at", ""),
            updated_at=doc.get("updated_at", ""),
            version=int(doc.get("version", 0)),
        )

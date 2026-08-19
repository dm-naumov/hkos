"""HKOS Campaign Validator (DS-005 §9, IP-005 Stage 3)
=====================================================
CampaignValidator проверяет кампанию и возвращает ValidationResult.

Проверки (только через CampaignRepository):
- существование кампании и корректность Repository;
- целостность UUID;
- соответствие Project (project задан);
- соответствие Schema Version;
- корректность состояния (легаси-статусы DS-003 — warning);
- наличие обязательных разделов: steps, journal;
- корректность ссылок на этапы (id этапов не пусты).

Валидатор НЕ изменяет Repository и НЕ бросает по результатам проверки.
"""

import re

from hkos.repository.campaign_repository import CampaignRepository
from hkos.repository.exceptions import (
    RepositoryNotFoundError,
    RepositoryParseError,
)
from hkos.services.campaign_state import VALID_CAMPAIGN_STATES
from hkos.services.project_validator import ValidationResult

__all__ = ["CampaignValidator"]

# Канонический формат UUID: 8-4-4-4-12 hex.
UUID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


class CampaignValidator:
    """Валидатор кампаний (единственная обязанность — проверка)."""

    def __init__(self, repository: CampaignRepository) -> None:
        """Инициализация валидатора.

        Args:
            repository: CampaignRepository из RepositoryManager.campaigns.
        """
        self._repository = repository

    def validate(self, project_id: str, campaign_id: str) -> ValidationResult:
        """Проверить кампанию.

        Args:
            project_id: UUID проекта-владельца.
            campaign_id: UUID кампании.

        Returns:
            ValidationResult с ошибками и предупреждениями.
        """
        errors: list[str] = []
        warnings: list[str] = []

        if not self._repository.exists(project_id, campaign_id):
            return ValidationResult(
                valid=False,
                errors=[f"Campaign not found: {campaign_id} in project {project_id}"],
            )

        try:
            campaign = self._repository.load(project_id, campaign_id)
        except (RepositoryNotFoundError, RepositoryParseError) as e:
            return ValidationResult(
                valid=False,
                errors=[f"Repository error for {campaign_id}: {e}"],
            )

        if not UUID_PATTERN.match(campaign.id):
            errors.append(f"Invalid UUID: {campaign.id!r}")
        if not campaign.project:
            errors.append("Campaign project is empty (mandatory field)")
        elif campaign.project != project_id:
            errors.append(
                f"Campaign project {campaign.project!r} does not match "
                f"requested project {project_id!r}"
            )
        if not campaign.goal:
            errors.append("Campaign goal is empty (mandatory field)")
        if not campaign.schema_version:
            errors.append("Schema version is empty (mandatory field)")
        # Строгая проверка состояния: легаси-статусы DS-003
        # ('active'/'closed') не имеют однозначного маппинга на состояния
        # DS-005 (READY/RUNNING/...), поэтому не допускаются.
        if campaign.status not in VALID_CAMPAIGN_STATES:
            errors.append(
                f"Invalid campaign state: {campaign.status!r}; "
                f"allowed: {sorted(VALID_CAMPAIGN_STATES)}"
            )
        for index, step in enumerate(campaign.steps):
            if not step.id:
                errors.append(f"Step #{index} has empty id (invalid step reference)")
        if not campaign.journal:
            warnings.append("Campaign journal is empty")

        return ValidationResult(valid=not errors, errors=errors, warnings=warnings)

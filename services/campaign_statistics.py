"""HKOS Campaign Statistics & Progress Engine (DS-005 §10-11, IP-005 Stage 4-5)
=================================================================================
Все значения — производные данные. Ничего не хранится вручную
и ничего не инкрементируется.

Progress Engine:
    progress = completed_steps / total_steps * 100
    (0% при отсутствии этапов; максимум 100%; FAILED этапы не считаются
    завершёнными и автоматически снижают процент).

Statistics Engine:
    CampaignStatistics.calculate(campaign) -> CampaignStatisticsResult
    (количество этапов, завершённых, FAILED, RETRY, длительность,
     created_at, updated_at, знания/решения/артефакты).
"""

from dataclasses import dataclass

from hkos.repository.models import Campaign, CampaignStep

__all__ = [
    "STEP_STATUS_PENDING",
    "STEP_STATUS_RUNNING",
    "STEP_STATUS_COMPLETED",
    "STEP_STATUS_FAILED",
    "CampaignStatisticsResult",
    "CampaignStatistics",
]

# Статусы этапов.
STEP_STATUS_PENDING: str = "pending"
STEP_STATUS_RUNNING: str = "running"
STEP_STATUS_COMPLETED: str = "completed"
STEP_STATUS_FAILED: str = "failed"

# Диапазон прогресса.
PROGRESS_MIN: int = 0
PROGRESS_MAX: int = 100


@dataclass
class CampaignStatisticsResult:
    """Результат расчёта статистики кампании (IP-005 §12)."""

    total_steps: int = 0
    completed_steps: int = 0
    failed_steps: int = 0
    retry_count: int = 0
    knowledge_count: int = 0
    decision_count: int = 0
    artifact_count: int = 0
    created_at: str = ""
    updated_at: str = ""
    duration: float = 0.0

    def as_dict(self) -> dict[str, object]:
        """Статистика как словарь."""
        return {
            "total_steps": self.total_steps,
            "completed_steps": self.completed_steps,
            "failed_steps": self.failed_steps,
            "retry_count": self.retry_count,
            "knowledge_count": self.knowledge_count,
            "decision_count": self.decision_count,
            "artifact_count": self.artifact_count,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "duration": self.duration,
        }


class CampaignStatistics:
    """Статистика и прогресс кампании (только вычисление, без хранения)."""

    @staticmethod
    def _iso_seconds(value: str) -> float:
        """Секунды с эпохи из ISO-8601; 0 при отсутствии/ошибке."""
        if not value:
            return 0.0
        try:
            from datetime import datetime

            return datetime.fromisoformat(value).timestamp()
        except ValueError:
            return 0.0

    @staticmethod
    def calculate_progress(steps: list[CampaignStep]) -> int:
        """Вычислить прогресс кампании (0..100).

        Args:
            steps: Этапы кампании (источник истины).

        Returns:
            Процент завершения: completed / total * 100.
            0 при отсутствии этапов; никогда не превышает 100.

        """
        total = len(steps)
        if total == 0:
            return PROGRESS_MIN
        completed = sum(
            1 for step in steps if step.status == STEP_STATUS_COMPLETED
        )
        progress = round(completed / total * PROGRESS_MAX)
        return max(PROGRESS_MIN, min(PROGRESS_MAX, progress))

    @classmethod
    def calculate(cls, campaign: Campaign) -> CampaignStatisticsResult:
        """Рассчитать статистику кампании.

        Args:
            campaign: Сущность Campaign (из Repository).

        Returns:
            CampaignStatisticsResult со всеми производными значениями.

        """
        steps = campaign.steps
        total = len(steps)
        completed = sum(1 for s in steps if s.status == STEP_STATUS_COMPLETED)
        failed = sum(1 for s in steps if s.status == STEP_STATUS_FAILED)
        retry_count = sum(1 for s in steps if s.retries > 0)

        created_ts = cls._iso_seconds(campaign.created_at)
        updated_ts = cls._iso_seconds(campaign.updated_at)
        duration = max(0.0, updated_ts - created_ts) if created_ts and updated_ts else 0.0

        return CampaignStatisticsResult(
            total_steps=total,
            completed_steps=completed,
            failed_steps=failed,
            retry_count=retry_count,
            # Связи с Knowledge/Decision не реализованы в DS-005
            # (IP-005, ARCHITECTURAL COMMENTS §7) — значения 0.
            knowledge_count=0,
            decision_count=0,
            artifact_count=len(campaign.artifacts),
            created_at=campaign.created_at,
            updated_at=campaign.updated_at,
            duration=duration,
        )

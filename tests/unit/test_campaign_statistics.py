"""Unit tests for Campaign Statistics & Progress Engine (IP-005 Stage 4-5)."""

from hkos.repository.models import Campaign, CampaignStep
from hkos.services.campaign_statistics import (
    STEP_STATUS_COMPLETED,
    STEP_STATUS_FAILED,
    STEP_STATUS_PENDING,
    CampaignStatistics,
)


class TestProgressEngine:
    """Progress вычисляется из этапов (никогда не хранится)."""

    def test_progress_no_steps_is_zero(self) -> None:
        assert CampaignStatistics.calculate_progress([]) == 0

    def test_progress_all_pending_is_zero(self) -> None:
        steps = [CampaignStep(id="1", status=STEP_STATUS_PENDING),
                 CampaignStep(id="2", status=STEP_STATUS_PENDING)]
        assert CampaignStatistics.calculate_progress(steps) == 0

    def test_progress_partial(self) -> None:
        steps = [CampaignStep(id="1", status=STEP_STATUS_COMPLETED),
                 CampaignStep(id="2", status=STEP_STATUS_PENDING),
                 CampaignStep(id="3", status=STEP_STATUS_PENDING)]
        assert CampaignStatistics.calculate_progress(steps) == 33

    def test_progress_all_completed_is_100(self) -> None:
        steps = [CampaignStep(id="1", status=STEP_STATUS_COMPLETED),
                 CampaignStep(id="2", status=STEP_STATUS_COMPLETED)]
        assert CampaignStatistics.calculate_progress(steps) == 100

    def test_progress_failed_not_completed(self) -> None:
        steps = [CampaignStep(id="1", status=STEP_STATUS_COMPLETED),
                 CampaignStep(id="2", status=STEP_STATUS_FAILED)]
        assert CampaignStatistics.calculate_progress(steps) == 50

    def test_progress_never_exceeds_100(self) -> None:
        steps = [CampaignStep(id=str(i), status=STEP_STATUS_COMPLETED) for i in range(5)]
        assert CampaignStatistics.calculate_progress(steps) == 100

    def test_progress_never_below_0(self) -> None:
        assert CampaignStatistics.calculate_progress([]) >= 0


class TestStatisticsEngine:
    """Statistics — только производные данные (IP-005 §12)."""

    def test_empty_campaign(self) -> None:
        result = CampaignStatistics.calculate(Campaign(id="c1"))
        assert result.total_steps == 0
        assert result.completed_steps == 0
        assert result.failed_steps == 0
        assert result.retry_count == 0

    def test_step_counts(self) -> None:
        campaign = Campaign(
            id="c1",
            steps=[
                CampaignStep(id="1", status=STEP_STATUS_COMPLETED),
                CampaignStep(id="2", status=STEP_STATUS_COMPLETED),
                CampaignStep(id="3", status=STEP_STATUS_FAILED),
                CampaignStep(id="4", status=STEP_STATUS_PENDING),
            ],
        )
        result = CampaignStatistics.calculate(campaign)
        assert result.total_steps == 4
        assert result.completed_steps == 2
        assert result.failed_steps == 1

    def test_retry_count(self) -> None:
        campaign = Campaign(
            id="c1",
            steps=[
                CampaignStep(id="1", status=STEP_STATUS_COMPLETED, retries=2),
                CampaignStep(id="2", status=STEP_STATUS_PENDING, retries=0),
                CampaignStep(id="3", status=STEP_STATUS_COMPLETED, retries=1),
            ],
        )
        assert CampaignStatistics.calculate(campaign).retry_count == 2

    def test_artifact_count(self) -> None:
        campaign = Campaign(id="c1", artifacts=["a.pdf", "b.pcap"])
        assert CampaignStatistics.calculate(campaign).artifact_count == 2

    def test_knowledge_and_decision_zero_in_ds005(self) -> None:
        campaign = Campaign(id="c1")
        result = CampaignStatistics.calculate(campaign)
        assert result.knowledge_count == 0
        assert result.decision_count == 0

    def test_created_updated_at_passthrough(self) -> None:
        campaign = Campaign(id="c1", created_at="2026-01-01T00:00:00+00:00",
                            updated_at="2026-01-01T01:00:00+00:00")
        result = CampaignStatistics.calculate(campaign)
        assert result.created_at == campaign.created_at
        assert result.updated_at == campaign.updated_at

    def test_duration_seconds(self) -> None:
        campaign = Campaign(id="c1", created_at="2026-01-01T00:00:00+00:00",
                            updated_at="2026-01-01T00:30:00+00:00")
        assert CampaignStatistics.calculate(campaign).duration == 1800.0

    def test_duration_zero_without_timestamps(self) -> None:
        assert CampaignStatistics.calculate(Campaign(id="c1")).duration == 0.0

    def test_as_dict_keys(self) -> None:
        result = CampaignStatistics.calculate(Campaign(id="c1"))
        assert set(result.as_dict().keys()) == {
            "total_steps", "completed_steps", "failed_steps", "retry_count",
            "knowledge_count", "decision_count", "artifact_count",
            "created_at", "updated_at", "duration",
        }

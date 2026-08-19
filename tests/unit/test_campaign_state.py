"""Unit tests for CampaignState machine (IP-005 Stage 1, DS-005 §8)."""

import pytest

from hkos.services.campaign_state import (
    CAMPAIGN_STATE_ARCHIVED,
    CAMPAIGN_STATE_COMPLETED,
    CAMPAIGN_STATE_CREATED,
    CAMPAIGN_STATE_FAILED,
    CAMPAIGN_STATE_PAUSED,
    CAMPAIGN_STATE_READY,
    CAMPAIGN_STATE_RUNNING,
    CAMPAIGN_STATE_WAITING_EXTERNAL,
    TRANSITIONS,
    VALID_CAMPAIGN_STATES,
    CampaignState,
)
from hkos.services.exceptions import CampaignStateError


class TestCampaignState:
    """Test suite for the Campaign finite state machine."""

    def test_valid_states(self) -> None:
        assert VALID_CAMPAIGN_STATES == frozenset({
            "CREATED", "READY", "RUNNING", "PAUSED",
            "WAITING_EXTERNAL", "FAILED", "COMPLETED", "ARCHIVED",
        })

    def test_initial_state(self) -> None:
        assert CampaignState(CAMPAIGN_STATE_CREATED).current == CAMPAIGN_STATE_CREATED

    def test_invalid_initial_state_raises(self) -> None:
        with pytest.raises(CampaignStateError):
            CampaignState("UNKNOWN")

    def test_created_to_ready(self) -> None:
        state = CampaignState(CAMPAIGN_STATE_CREATED)
        state.transition_to(CAMPAIGN_STATE_READY)
        assert state.current == CAMPAIGN_STATE_READY

    def test_ready_to_running(self) -> None:
        state = CampaignState(CAMPAIGN_STATE_READY)
        state.transition_to(CAMPAIGN_STATE_RUNNING)
        assert state.current == CAMPAIGN_STATE_RUNNING

    def test_running_to_paused_and_back(self) -> None:
        state = CampaignState(CAMPAIGN_STATE_RUNNING)
        state.transition_to(CAMPAIGN_STATE_PAUSED)
        assert state.current == CAMPAIGN_STATE_PAUSED
        state.transition_to(CAMPAIGN_STATE_RUNNING)
        assert state.current == CAMPAIGN_STATE_RUNNING

    def test_running_to_waiting_external_and_back(self) -> None:
        state = CampaignState(CAMPAIGN_STATE_RUNNING)
        state.transition_to(CAMPAIGN_STATE_WAITING_EXTERNAL)
        assert state.current == CAMPAIGN_STATE_WAITING_EXTERNAL
        state.transition_to(CAMPAIGN_STATE_RUNNING)
        assert state.current == CAMPAIGN_STATE_RUNNING

    def test_running_to_completed_to_archived(self) -> None:
        state = CampaignState(CAMPAIGN_STATE_RUNNING)
        state.transition_to(CAMPAIGN_STATE_COMPLETED)
        state.transition_to(CAMPAIGN_STATE_ARCHIVED)
        assert state.current == CAMPAIGN_STATE_ARCHIVED

    def test_failed_from_ready(self) -> None:
        state = CampaignState(CAMPAIGN_STATE_READY)
        state.transition_to(CAMPAIGN_STATE_FAILED)
        assert state.current == CAMPAIGN_STATE_FAILED

    def test_failed_from_running(self) -> None:
        state = CampaignState(CAMPAIGN_STATE_RUNNING)
        state.transition_to(CAMPAIGN_STATE_FAILED)
        assert state.current == CAMPAIGN_STATE_FAILED

    def test_failed_from_paused(self) -> None:
        state = CampaignState(CAMPAIGN_STATE_PAUSED)
        state.transition_to(CAMPAIGN_STATE_FAILED)
        assert state.current == CAMPAIGN_STATE_FAILED

    def test_failed_from_waiting_external(self) -> None:
        state = CampaignState(CAMPAIGN_STATE_WAITING_EXTERNAL)
        state.transition_to(CAMPAIGN_STATE_FAILED)
        assert state.current == CAMPAIGN_STATE_FAILED

    def test_failed_to_archived(self) -> None:
        state = CampaignState(CAMPAIGN_STATE_FAILED)
        state.transition_to(CAMPAIGN_STATE_ARCHIVED)
        assert state.current == CAMPAIGN_STATE_ARCHIVED

    def test_archived_to_running_forbidden(self) -> None:
        state = CampaignState(CAMPAIGN_STATE_ARCHIVED)
        with pytest.raises(CampaignStateError):
            state.transition_to(CAMPAIGN_STATE_RUNNING)

    def test_archived_to_ready_forbidden(self) -> None:
        state = CampaignState(CAMPAIGN_STATE_ARCHIVED)
        with pytest.raises(CampaignStateError):
            state.transition_to(CAMPAIGN_STATE_READY)

    def test_failed_to_running_forbidden(self) -> None:
        state = CampaignState(CAMPAIGN_STATE_FAILED)
        with pytest.raises(CampaignStateError):
            state.transition_to(CAMPAIGN_STATE_RUNNING)

    def test_completed_to_running_forbidden(self) -> None:
        state = CampaignState(CAMPAIGN_STATE_COMPLETED)
        with pytest.raises(CampaignStateError):
            state.transition_to(CAMPAIGN_STATE_RUNNING)

    def test_created_to_running_forbidden(self) -> None:
        state = CampaignState(CAMPAIGN_STATE_CREATED)
        with pytest.raises(CampaignStateError):
            state.transition_to(CAMPAIGN_STATE_RUNNING)

    def test_archived_is_terminal(self) -> None:
        state = CampaignState(CAMPAIGN_STATE_ARCHIVED)
        for target in VALID_CAMPAIGN_STATES - {CAMPAIGN_STATE_ARCHIVED}:
            with pytest.raises(CampaignStateError):
                state.transition_to(target)

    def test_invalid_target_raises(self) -> None:
        state = CampaignState(CAMPAIGN_STATE_CREATED)
        with pytest.raises(CampaignStateError):
            state.transition_to("NOPE")

    def test_transition_table_complete(self) -> None:
        assert set(TRANSITIONS.keys()) == set(VALID_CAMPAIGN_STATES)

    def test_error_message_contains_transition(self) -> None:
        state = CampaignState(CAMPAIGN_STATE_ARCHIVED)
        with pytest.raises(CampaignStateError, match="ARCHIVED -> RUNNING"):
            state.transition_to(CAMPAIGN_STATE_RUNNING)

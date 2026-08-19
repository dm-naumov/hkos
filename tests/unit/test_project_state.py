"""Unit tests for ProjectState machine (DS-004 §9, IP-004 этап 02)."""

import pytest

from hkos.services.exceptions import ProjectStateError
from hkos.services.project_state import (
    PROJECT_STATE_ACTIVE,
    PROJECT_STATE_ARCHIVED,
    PROJECT_STATE_CREATED,
    PROJECT_STATE_DELETED,
    PROJECT_STATE_PAUSED,
    TRANSITIONS,
    VALID_PROJECT_STATES,
    ProjectState,
)


class TestProjectState:
    """Test suite for the Project finite state machine."""

    def test_valid_states(self) -> None:
        assert VALID_PROJECT_STATES == frozenset({
            "CREATED", "ACTIVE", "PAUSED", "ARCHIVED", "DELETED",
        })

    def test_initial_state(self) -> None:
        state = ProjectState(PROJECT_STATE_CREATED)
        assert state.current == PROJECT_STATE_CREATED

    def test_invalid_initial_state_raises(self) -> None:
        with pytest.raises(ProjectStateError):
            ProjectState("UNKNOWN")

    def test_created_to_active(self) -> None:
        state = ProjectState(PROJECT_STATE_CREATED)
        state.transition_to(PROJECT_STATE_ACTIVE)
        assert state.current == PROJECT_STATE_ACTIVE

    def test_active_to_paused_and_back(self) -> None:
        state = ProjectState(PROJECT_STATE_ACTIVE)
        state.transition_to(PROJECT_STATE_PAUSED)
        assert state.current == PROJECT_STATE_PAUSED
        state.transition_to(PROJECT_STATE_ACTIVE)
        assert state.current == PROJECT_STATE_ACTIVE

    def test_archive_from_created(self) -> None:
        state = ProjectState(PROJECT_STATE_CREATED)
        state.transition_to(PROJECT_STATE_ARCHIVED)
        assert state.current == PROJECT_STATE_ARCHIVED

    def test_archived_to_deleted(self) -> None:
        state = ProjectState(PROJECT_STATE_ARCHIVED)
        state.transition_to(PROJECT_STATE_DELETED)
        assert state.current == PROJECT_STATE_DELETED

    def test_archived_to_active_forbidden(self) -> None:
        state = ProjectState(PROJECT_STATE_ARCHIVED)
        with pytest.raises(ProjectStateError):
            state.transition_to(PROJECT_STATE_ACTIVE)

    def test_deleted_is_terminal(self) -> None:
        state = ProjectState(PROJECT_STATE_DELETED)
        for target in VALID_PROJECT_STATES - {PROJECT_STATE_DELETED}:
            with pytest.raises(ProjectStateError):
                state.transition_to(target)

    def test_invalid_target_raises(self) -> None:
        state = ProjectState(PROJECT_STATE_CREATED)
        with pytest.raises(ProjectStateError):
            state.transition_to("NOPE")

    def test_transition_table_complete(self) -> None:
        """Каждое допустимое состояние присутствует в таблице."""
        assert set(TRANSITIONS.keys()) == set(VALID_PROJECT_STATES)

    def test_error_message_contains_transition(self) -> None:
        state = ProjectState(PROJECT_STATE_ARCHIVED)
        with pytest.raises(ProjectStateError, match="ARCHIVED -> ACTIVE"):
            state.transition_to(PROJECT_STATE_ACTIVE)

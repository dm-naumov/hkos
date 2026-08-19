"""Unit tests for KnowledgeStatus (DS-006 §9, IP-006 §10)."""

import pytest

from hkos.repository.models import Knowledge
from hkos.services.librarian.exceptions import KnowledgeStatusError
from hkos.services.librarian.knowledge_status import (
    KNOWLEDGE_STATUS_ARCHIVED,
    KNOWLEDGE_STATUS_CANONICAL,
    KNOWLEDGE_STATUS_CONFLICT,
    KNOWLEDGE_STATUS_NEW,
    KNOWLEDGE_STATUS_REJECTED,
    KNOWLEDGE_STATUS_SUPERSEDED,
    KNOWLEDGE_STATUS_VERIFIED,
    TRANSITIONS,
    VALID_KNOWLEDGE_STATUSES,
    KnowledgeStatus,
)


class TestKnowledgeStatus:
    """Test suite for Knowledge status machine."""

    def test_valid_statuses(self) -> None:
        assert VALID_KNOWLEDGE_STATUSES == frozenset({
            "NEW", "VERIFIED", "CANONICAL", "SUPERSEDED",
            "CONFLICT", "REJECTED", "ARCHIVED",
        })

    def test_main_path(self) -> None:
        result = KnowledgeStatus.transition(
            KNOWLEDGE_STATUS_NEW, KNOWLEDGE_STATUS_VERIFIED
        )
        assert result == KNOWLEDGE_STATUS_VERIFIED
        result = KnowledgeStatus.transition(
            KNOWLEDGE_STATUS_VERIFIED, KNOWLEDGE_STATUS_CANONICAL
        )
        assert result == KNOWLEDGE_STATUS_CANONICAL
        result = KnowledgeStatus.transition(
            KNOWLEDGE_STATUS_CANONICAL, KNOWLEDGE_STATUS_SUPERSEDED
        )
        assert result == KNOWLEDGE_STATUS_SUPERSEDED
        result = KnowledgeStatus.transition(
            KNOWLEDGE_STATUS_SUPERSEDED, KNOWLEDGE_STATUS_ARCHIVED
        )
        assert result == KNOWLEDGE_STATUS_ARCHIVED

    def test_new_to_rejected(self) -> None:
        result = KnowledgeStatus.transition(
            KNOWLEDGE_STATUS_NEW, KNOWLEDGE_STATUS_REJECTED
        )
        assert result == KNOWLEDGE_STATUS_REJECTED

    def test_new_to_conflict(self) -> None:
        result = KnowledgeStatus.transition(
            KNOWLEDGE_STATUS_NEW, KNOWLEDGE_STATUS_CONFLICT
        )
        assert result == KNOWLEDGE_STATUS_CONFLICT

    def test_new_to_canonical_forbidden(self) -> None:
        with pytest.raises(KnowledgeStatusError):
            KnowledgeStatus.transition(KNOWLEDGE_STATUS_NEW, KNOWLEDGE_STATUS_CANONICAL)

    def test_archived_to_verified_restore(self) -> None:
        result = KnowledgeStatus.transition(
            KNOWLEDGE_STATUS_ARCHIVED, KNOWLEDGE_STATUS_VERIFIED
        )
        assert result == KNOWLEDGE_STATUS_VERIFIED

    def test_rejected_to_canonical_forbidden(self) -> None:
        with pytest.raises(KnowledgeStatusError):
            KnowledgeStatus.transition(KNOWLEDGE_STATUS_REJECTED, KNOWLEDGE_STATUS_CANONICAL)

    def test_invalid_current_raises(self) -> None:
        with pytest.raises(KnowledgeStatusError):
            KnowledgeStatus.transition("LIMBO", KNOWLEDGE_STATUS_VERIFIED)

    def test_invalid_target_raises(self) -> None:
        with pytest.raises(KnowledgeStatusError):
            KnowledgeStatus.transition(KNOWLEDGE_STATUS_NEW, "LIMBO")

    def test_table_complete(self) -> None:
        assert set(TRANSITIONS.keys()) == set(VALID_KNOWLEDGE_STATUSES)

    def test_predicates(self) -> None:
        k_new = Knowledge(id="1", status=KNOWLEDGE_STATUS_NEW)
        k_ver = Knowledge(id="2", status=KNOWLEDGE_STATUS_VERIFIED)
        k_can = Knowledge(id="3", status=KNOWLEDGE_STATUS_CANONICAL)
        k_arch = Knowledge(id="4", status=KNOWLEDGE_STATUS_ARCHIVED)
        assert KnowledgeStatus.is_new(k_new)
        assert KnowledgeStatus.is_verified(k_ver)
        assert KnowledgeStatus.is_canonical(k_can)
        assert KnowledgeStatus.is_archived(k_arch)
        assert not KnowledgeStatus.is_verified(k_new)
        assert KnowledgeStatus.is_active(k_ver)
        assert not KnowledgeStatus.is_active(k_arch)

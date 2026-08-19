"""Unit tests for ConflictDetector (DS-006 §11, IP-006 §5)."""

from hkos.repository.models import Knowledge
from hkos.services.librarian.conflict_detector import ConflictDetector
from hkos.services.librarian.knowledge_classifier import CATEGORY_FAILURE


class TestConflictDetector:
    """Detector отвечает только YES/NO + confidence; статусы не меняет."""

    def test_no_conflict(self) -> None:
        candidate = Knowledge(id="1", title="TProxy UDP works", kind="fact")
        others = [Knowledge(id="2", title="Different topic")]
        result = ConflictDetector.detect(candidate, others)
        assert result.conflict_exists is False
        assert result.confidence_of_conflict == 0.0
        assert result.conflicting == []

    def test_opposite_polarity_conflict(self) -> None:
        candidate = Knowledge(id="1", title="TProxy UDP works", kind="fact")
        others = [Knowledge(id="2", title="tproxy udp works", kind="negative")]
        result = ConflictDetector.detect(candidate, others)
        assert result.conflict_exists is True
        assert result.confidence_of_conflict == 1.0
        assert [k.id for k in result.conflicting] == ["2"]

    def test_failure_category_conflicts_with_success(self) -> None:
        candidate = Knowledge(id="1", title="X", category=CATEGORY_FAILURE)
        others = [Knowledge(id="2", title="x", category="SUCCESS")]
        result = ConflictDetector.detect(candidate, others)
        assert result.conflict_exists is True

    def test_same_polarity_no_conflict(self) -> None:
        candidate = Knowledge(id="1", title="X", kind="negative")
        others = [Knowledge(id="2", title="x", kind="negative")]
        result = ConflictDetector.detect(candidate, others)
        assert result.conflict_exists is False

    def test_newer_version_conflict(self) -> None:
        candidate = Knowledge(id="1", title="X", created_at="2026-01-01T00:00:00+00:00")
        others = [Knowledge(id="2", title="x", created_at="2026-02-01T00:00:00+00:00")]
        result = ConflictDetector.detect(candidate, others)
        assert result.conflict_exists is True

    def test_does_not_change_status(self) -> None:
        candidate = Knowledge(id="1", title="X", status="NEW")
        others = [Knowledge(id="2", title="x", kind="negative")]
        ConflictDetector.detect(candidate, others)
        assert candidate.status == "NEW"

    def test_empty_title_no_conflict(self) -> None:
        candidate = Knowledge(id="1", title="")
        others = [Knowledge(id="2", title="", kind="negative")]
        result = ConflictDetector.detect(candidate, others)
        assert result.conflict_exists is False

    def test_as_dict(self) -> None:
        candidate = Knowledge(id="1", title="X")
        others = [Knowledge(id="2", title="x", kind="negative")]
        result = ConflictDetector.detect(candidate, others)
        d = result.as_dict()
        assert d["conflict_exists"] is True
        assert d["conflicting_ids"] == ["2"]

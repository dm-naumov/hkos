"""Unit tests: LatencyTracker (DS-013 ЭТАП 4)."""

from hkos.performance.latency_tracker import LatencyTracker


class TestLatencyTracker:
    """История задержек: record/recent/average/percentile."""

    def test_record_recent(self) -> None:
        tracker = LatencyTracker()
        for i in range(5):
            tracker.record("retrieval", float(i))
        assert tracker.recent("retrieval") == [0.0, 1.0, 2.0, 3.0, 4.0]
        assert tracker.recent("retrieval", limit=2) == [3.0, 4.0]
        assert tracker.recent("unknown") == []

    def test_average(self) -> None:
        tracker = LatencyTracker()
        tracker.record("op", 10.0)
        tracker.record("op", 20.0)
        assert tracker.average("op") == 15.0
        assert tracker.average("none") is None

    def test_percentiles(self) -> None:
        tracker = LatencyTracker()
        for i in range(1, 101):
            tracker.record("op", float(i))
        p50 = tracker.percentile("op", 50)
        p95 = tracker.percentile("op", 95)
        p99 = tracker.percentile("op", 99)
        assert p50 is not None and 49 <= p50 <= 51
        assert p95 is not None and 94 <= p95 <= 96
        assert p99 is not None and 98 <= p99 <= 100
        assert tracker.percentile("none", 50) is None

"""Unit tests: MigrationHistory (DS-011 §14, IP-011 ЭТАП 4)."""

from hkos.migration.migration_history import (
    STATUS_APPLIED,
    STATUS_ROLLED_BACK,
    MigrationHistory,
    MigrationRecord,
)


def _record(migration_id: str = "001", status: str = STATUS_APPLIED,
            rolled_back: bool = False) -> MigrationRecord:
    return MigrationRecord(
        migration_id=migration_id, timestamp="2026-08-07T00:00:00Z",
        agent="test", from_version=1, to_version=2,
        status=status, duration_ms=10, rolled_back=rolled_back,
    )


class TestMigrationHistory:
    """Append-only event log: несколько записей на миграцию, без дедупликации."""

    def test_append_and_entries_order(self) -> None:
        history = MigrationHistory()
        history.append(_record("001"))
        history.append(_record("002"))
        entries = history.entries()
        assert [e.migration_id for e in entries] == ["001", "002"]

    def test_multiple_records_per_migration(self) -> None:
        """Несколько записей одной миграции — допускаются, без дедупликации."""
        history = MigrationHistory()
        history.append(_record("001"))
        history.append(_record("001", status=STATUS_ROLLED_BACK, rolled_back=True))
        history.append(_record("001"))  # повторная попытка
        assert len(history.entries()) == 3

    def test_last(self) -> None:
        history = MigrationHistory()
        assert history.last() is None
        history.append(_record("001"))
        history.append(_record("002"))
        assert history.last() is not None
        assert history.last().migration_id == "002"  # type: ignore[union-attr]

    def test_last_success(self) -> None:
        history = MigrationHistory()
        history.append(_record("001", status=STATUS_ROLLED_BACK, rolled_back=True))
        history.append(_record("001"))
        last = history.last_success()
        assert last is not None
        assert last.migration_id == "001"
        assert last.rolled_back is False

    def test_last_success_none(self) -> None:
        history = MigrationHistory()
        history.append(_record("001", status=STATUS_ROLLED_BACK, rolled_back=True))
        assert history.last_success() is None

    def test_last_for_migration(self) -> None:
        history = MigrationHistory()
        history.append(_record("001"))
        history.append(_record("002"))
        history.append(_record("001"))
        last = history.last_for_migration("001")
        assert last is not None
        assert last.migration_id == "001"
        assert history.last_for_migration("nope") is None

    def test_deterministic(self) -> None:
        history = MigrationHistory()
        history.append(_record("001"))
        history.append(_record("002"))
        assert history.entries() == history.entries()

    def test_entries_returns_copy(self) -> None:
        history = MigrationHistory()
        history.append(_record("001"))
        entries = history.entries()
        entries.append(_record("002"))  # мутация копии
        assert len(history.entries()) == 1

    def test_no_clear(self) -> None:
        """clear() НЕ реализован (append-only)."""
        assert not hasattr(MigrationHistory, "clear")
        api = {m for m in dir(MigrationHistory) if not m.startswith("_")}
        assert api <= {"append", "entries", "last", "last_success", "last_for_migration"}

    def test_append_only_no_mutation_api(self) -> None:
        history = MigrationHistory()
        history.append(_record("001"))
        # нет API удаления/изменения
        assert not hasattr(history, "remove")
        assert not hasattr(history, "update")

"""Unit tests: AgentLock (DS-012 ЭТАП 4 §7)."""

import threading
import time

from hkos.integration.hermes.agent_lock import (
    LOCK_MODE_MIGRATION,
    LOCK_MODE_READ,
    LOCK_MODE_WRITE,
    AgentLock,
)


class TestAgentLock:
    """READ: много агентов; WRITE: один; MIGRATION: эксклюзив."""

    def test_multiple_readers(self) -> None:
        lock = AgentLock()
        lock.acquire(LOCK_MODE_READ)
        lock.acquire(LOCK_MODE_READ)  # второй читатель
        assert lock.readers == 2
        lock.release(LOCK_MODE_READ)
        lock.release(LOCK_MODE_READ)
        assert lock.readers == 0

    def test_concurrent_write_exclusive(self) -> None:
        """Второй писатель ждёт завершения первого."""
        lock = AgentLock()
        order: list[str] = []

        def writer_a() -> None:
            lock.acquire(LOCK_MODE_WRITE)
            order.append("a-start")
            time.sleep(0.1)
            order.append("a-end")
            lock.release(LOCK_MODE_WRITE)

        def writer_b() -> None:
            time.sleep(0.02)
            lock.acquire(LOCK_MODE_WRITE)
            order.append("b-start")
            lock.release(LOCK_MODE_WRITE)

        threads = [threading.Thread(target=writer_a),
                   threading.Thread(target=writer_b)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert order == ["a-start", "a-end", "b-start"]  # b ждал a

    def test_migration_exclusive(self) -> None:
        """MIGRATION блокирует читателей."""
        lock = AgentLock()
        lock.acquire(LOCK_MODE_MIGRATION)
        blocked: list[bool] = [True]

        def reader() -> None:
            lock.acquire(LOCK_MODE_READ)
            blocked[0] = False
            lock.release(LOCK_MODE_READ)

        t = threading.Thread(target=reader)
        t.start()
        time.sleep(0.05)
        assert blocked[0] is True  # читатель заблокирован миграцией
        lock.release(LOCK_MODE_MIGRATION)
        t.join(timeout=1)
        assert blocked[0] is False  # после снятия — доступен

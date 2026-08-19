"""Hermes Failure Isolation (DS-012 ЭТАП 4 §6)
==============================================
Graceful degradation: HKOS не является single point of failure.

- Retrieval недоступен -> пустой контекст + warning + продолжение;
- Librarian недоступен -> pending knowledge queue (результат не теряется);
- Snapshot недоступен -> retrieval без Snapshot.
"""

from typing import Final

from hkos.core.logger import HKOSLogger

__all__ = ["FallbackPolicy"]

FALLBACK_EMPTY_CONTEXT: Final[str] = "empty_context"
FALLBACK_PENDING_QUEUE: Final[str] = "pending_queue"
FALLBACK_NO_SNAPSHOT: Final[str] = "retrieval_without_snapshot"


class FallbackPolicy:
    """Политика деградации при недоступности подсистем."""

    def __init__(self, logger: HKOSLogger | None = None) -> None:
        """Инициализация.

        Args:
            logger: Логгер (warning фиксируются).

        """
        self._logger = logger or HKOSLogger()
        self._pending: list[object] = []

    def retrieval_unavailable(self, agent_id: str = "") -> list[object]:
        """Retrieval недоступен: пустой контекст + warning + continue.

        Returns:
            Пустой список результатов (контекст без содержимого).

        """
        self._logger.warning(
            f"Fallback: retrieval unavailable (agent={agent_id or 'unknown'})"
        )
        return []

    def librarian_unavailable(self, knowledge: object) -> None:
        """Librarian недоступен: знание в pending queue (не теряется)."""
        self._pending.append(knowledge)
        self._logger.warning(
            f"Fallback: librarian unavailable; knowledge queued ({len(self._pending)})"
        )

    def snapshot_unavailable(self) -> bool:
        """Snapshot недоступен: retrieval продолжается без Snapshot.

        Returns:
            True — использовать retrieval без Snapshot.

        """
        self._logger.warning("Fallback: snapshot unavailable; retrieval without snapshot")
        return True

    def pending_count(self) -> int:
        """Размер очереди ожидающих знаний."""
        return len(self._pending)

    def drain_pending(self) -> list[object]:
        """Забрать и очистить очередь (для повторной попытки записи)."""
        pending = self._pending
        self._pending = []
        return pending

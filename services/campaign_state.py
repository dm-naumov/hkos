"""HKOS Campaign State Machine (DS-005 §8, IP-005 §8)
================================================
Конечный автомат жизненного цикла Campaign.

Допустимые состояния (только эти):
    CREATED, READY, RUNNING, PAUSED, WAITING_EXTERNAL,
    FAILED, COMPLETED, ARCHIVED

Таблица TRANSITIONS — единственный источник правил переходов.
Любой запрещённый переход -> CampaignStateError (без автопочинки).
CampaignState является единственным компонентом, определяющим
допустимость переходов (IP-005 §3.1).
"""

from hkos.services.exceptions import CampaignStateError

__all__ = [
    "CAMPAIGN_STATE_CREATED",
    "CAMPAIGN_STATE_READY",
    "CAMPAIGN_STATE_RUNNING",
    "CAMPAIGN_STATE_PAUSED",
    "CAMPAIGN_STATE_WAITING_EXTERNAL",
    "CAMPAIGN_STATE_FAILED",
    "CAMPAIGN_STATE_COMPLETED",
    "CAMPAIGN_STATE_ARCHIVED",
    "VALID_CAMPAIGN_STATES",
    "TRANSITIONS",
    "CampaignState",
]

CAMPAIGN_STATE_CREATED: str = "CREATED"
CAMPAIGN_STATE_READY: str = "READY"
CAMPAIGN_STATE_RUNNING: str = "RUNNING"
CAMPAIGN_STATE_PAUSED: str = "PAUSED"
CAMPAIGN_STATE_WAITING_EXTERNAL: str = "WAITING_EXTERNAL"
CAMPAIGN_STATE_FAILED: str = "FAILED"
CAMPAIGN_STATE_COMPLETED: str = "COMPLETED"
CAMPAIGN_STATE_ARCHIVED: str = "ARCHIVED"

VALID_CAMPAIGN_STATES: frozenset[str] = frozenset({
    CAMPAIGN_STATE_CREATED,
    CAMPAIGN_STATE_READY,
    CAMPAIGN_STATE_RUNNING,
    CAMPAIGN_STATE_PAUSED,
    CAMPAIGN_STATE_WAITING_EXTERNAL,
    CAMPAIGN_STATE_FAILED,
    CAMPAIGN_STATE_COMPLETED,
    CAMPAIGN_STATE_ARCHIVED,
})

# Таблица переходов (IP-005 §8, DS-005 §8):
#   CREATED -> READY
#   READY -> RUNNING | FAILED
#   RUNNING -> PAUSED | WAITING_EXTERNAL | COMPLETED | FAILED
#   PAUSED -> RUNNING | FAILED
#   WAITING_EXTERNAL -> RUNNING | FAILED
#   FAILED -> ARCHIVED
#   COMPLETED -> ARCHIVED
#   ARCHIVED -> (терминальное)
# Запрещены: ARCHIVED -> RUNNING/READY, FAILED -> RUNNING,
# COMPLETED -> RUNNING (восстановление не реализовано в Sprint 5).
TRANSITIONS: dict[str, frozenset[str]] = {
    CAMPAIGN_STATE_CREATED: frozenset({CAMPAIGN_STATE_READY}),
    CAMPAIGN_STATE_READY: frozenset({
        CAMPAIGN_STATE_RUNNING,
        CAMPAIGN_STATE_FAILED,
    }),
    CAMPAIGN_STATE_RUNNING: frozenset({
        CAMPAIGN_STATE_PAUSED,
        CAMPAIGN_STATE_WAITING_EXTERNAL,
        CAMPAIGN_STATE_COMPLETED,
        CAMPAIGN_STATE_FAILED,
    }),
    CAMPAIGN_STATE_PAUSED: frozenset({
        CAMPAIGN_STATE_RUNNING,
        CAMPAIGN_STATE_FAILED,
    }),
    CAMPAIGN_STATE_WAITING_EXTERNAL: frozenset({
        CAMPAIGN_STATE_RUNNING,
        CAMPAIGN_STATE_FAILED,
    }),
    CAMPAIGN_STATE_FAILED: frozenset({CAMPAIGN_STATE_ARCHIVED}),
    CAMPAIGN_STATE_COMPLETED: frozenset({CAMPAIGN_STATE_ARCHIVED}),
    CAMPAIGN_STATE_ARCHIVED: frozenset(),
}


class CampaignState:
    """Конечный автомат состояния кампании.

    Usage:
        state = CampaignState("CREATED")
        state.transition_to("READY")
        state.current == "READY"
    """

    def __init__(self, current: str) -> None:
        """Инициализация с текущим состоянием.

        Args:
            current: Начальное состояние (должно быть допустимым).

        Raises:
            CampaignStateError: Если состояние не входит в
                VALID_CAMPAIGN_STATES.
        """
        if current not in VALID_CAMPAIGN_STATES:
            raise CampaignStateError(
                f"Invalid campaign state: {current!r}; "
                f"allowed: {sorted(VALID_CAMPAIGN_STATES)}"
            )
        self._current: str = current

    @property
    def current(self) -> str:
        """Текущее состояние."""
        return self._current

    def transition_to(self, target: str) -> None:
        """Выполнить переход в target.

        Args:
            target: Целевое состояние.

        Raises:
            CampaignStateError: Если переход запрещён таблицей
                TRANSITIONS или целевое состояние недопустимо.
        """
        if target not in VALID_CAMPAIGN_STATES:
            raise CampaignStateError(
                f"Invalid target state: {target!r}; "
                f"allowed: {sorted(VALID_CAMPAIGN_STATES)}"
            )
        allowed = TRANSITIONS[self._current]
        if target not in allowed:
            raise CampaignStateError(
                f"Illegal campaign state transition: "
                f"{self._current} -> {target}; "
                f"allowed from {self._current}: {sorted(allowed)}"
            )
        self._current = target

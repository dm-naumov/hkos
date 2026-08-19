"""HKOS Project State Machine (DS-004 §9)
========================================
Конечный автомат жизненного цикла Project.

Допустимые состояния (только эти):
    CREATED, ACTIVE, PAUSED, ARCHIVED, DELETED

Переходы описаны таблицей TRANSITIONS. Любой запрещённый переход
генерирует ProjectStateError. DELETED — терминальное состояние.
"""

from hkos.services.exceptions import ProjectStateError

__all__ = [
    "PROJECT_STATE_CREATED",
    "PROJECT_STATE_ACTIVE",
    "PROJECT_STATE_PAUSED",
    "PROJECT_STATE_ARCHIVED",
    "PROJECT_STATE_DELETED",
    "VALID_PROJECT_STATES",
    "TRANSITIONS",
    "ProjectState",
]

PROJECT_STATE_CREATED: str = "CREATED"
PROJECT_STATE_ACTIVE: str = "ACTIVE"
PROJECT_STATE_PAUSED: str = "PAUSED"
PROJECT_STATE_ARCHIVED: str = "ARCHIVED"
PROJECT_STATE_DELETED: str = "DELETED"

VALID_PROJECT_STATES: frozenset[str] = frozenset({
    PROJECT_STATE_CREATED,
    PROJECT_STATE_ACTIVE,
    PROJECT_STATE_PAUSED,
    PROJECT_STATE_ARCHIVED,
    PROJECT_STATE_DELETED,
})

# Таблица переходов: current -> set(допустимые target).
# ARCHIVED -> ACTIVE запрещён (DS-004 §9) без операции восстановления.
# DELETED — терминальное состояние.
TRANSITIONS: dict[str, frozenset[str]] = {
    PROJECT_STATE_CREATED: frozenset({
        PROJECT_STATE_ACTIVE,
        PROJECT_STATE_ARCHIVED,
        PROJECT_STATE_DELETED,
    }),
    PROJECT_STATE_ACTIVE: frozenset({
        PROJECT_STATE_PAUSED,
        PROJECT_STATE_ARCHIVED,
        PROJECT_STATE_DELETED,
    }),
    PROJECT_STATE_PAUSED: frozenset({
        PROJECT_STATE_ACTIVE,
        PROJECT_STATE_ARCHIVED,
        PROJECT_STATE_DELETED,
    }),
    PROJECT_STATE_ARCHIVED: frozenset({
        PROJECT_STATE_DELETED,
    }),
    PROJECT_STATE_DELETED: frozenset(),
}


class ProjectState:
    """Конечный автомат состояния проекта.

    Usage:
        state = ProjectState("CREATED")
        state.transition_to("ACTIVE")
        state.current == "ACTIVE"
    """

    def __init__(self, current: str) -> None:
        """Инициализация с текущим состоянием.

        Args:
            current: Начальное состояние (должно быть допустимым).

        Raises:
            ProjectStateError: Если состояние не входит в VALID_PROJECT_STATES.
        """
        if current not in VALID_PROJECT_STATES:
            raise ProjectStateError(
                f"Invalid project state: {current!r}; "
                f"allowed: {sorted(VALID_PROJECT_STATES)}"
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
            ProjectStateError: Если переход запрещён таблицей TRANSITIONS
                или целевое состояние недопустимо.
        """
        if target not in VALID_PROJECT_STATES:
            raise ProjectStateError(
                f"Invalid target state: {target!r}; "
                f"allowed: {sorted(VALID_PROJECT_STATES)}"
            )
        allowed = TRANSITIONS[self._current]
        if target not in allowed:
            raise ProjectStateError(
                f"Illegal project state transition: "
                f"{self._current} -> {target}; "
                f"allowed from {self._current}: {sorted(allowed)}"
            )
        self._current = target

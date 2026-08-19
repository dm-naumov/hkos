"""HKOS Runtime State
===================
Manages the lifecycle state of HKOS.
"""

from dataclasses import dataclass
from typing import Any, Literal

from hkos.core.constants import (
    STATE_ERROR,
    STATE_INITIALIZED,
    STATE_RUNNING,
    STATE_STARTED,
    STATE_STOPPED,
    STATE_STOPPING,
)

StateName = Literal[
    "started", "initialized", "running", "stopping", "stopped", "error"
]


@dataclass
class RuntimeState:
    """Runtime state of the HKOS engine.
    
    Tracks the lifecycle of HKOS through its states.
    Immutable after initialization — state transitions are explicit.
    """

    started: bool = False
    initialized: bool = False
    running: bool = False
    stopping: bool = False

    def transition_to(self, state: StateName) -> None:
        """Transition to a new state. Validates allowed transitions."""
        transitions = {
            STATE_STARTED: lambda: self._reset(),
            STATE_INITIALIZED: lambda: self._set_all(started=True, initialized=True),
            STATE_RUNNING: lambda: self._set_all(started=True, initialized=True, running=True),
            STATE_STOPPING: lambda: self._set_all(started=True, initialized=True, stopping=True),
            STATE_STOPPED: lambda: self._reset(),
            STATE_ERROR: lambda: self._set_all(started=True, initialized=True, running=False, stopping=False),
        }
        if state in transitions:
            transitions[state]()
        else:
            raise ValueError(f"Unknown state: {state}")

    def _reset(self) -> None:
        self.started = False
        self.initialized = False
        self.running = False
        self.stopping = False

    def _set_all(
        self,
        started: bool = False,
        initialized: bool = False,
        running: bool = False,
        stopping: bool = False,
    ) -> None:
        self.started = started
        self.initialized = initialized
        self.running = running
        self.stopping = stopping

    def current(self) -> str:
        """Return the current state name."""
        if self.stopping:
            return STATE_STOPPING
        if self.running:
            return STATE_RUNNING
        if self.initialized:
            return STATE_INITIALIZED
        if self.started:
            return STATE_STARTED
        return STATE_STOPPED

    def dict(self) -> dict[str, Any]:
        return {
            "state": self.current(),
            "started": self.started,
            "initialized": self.initialized,
            "running": self.running,
            "stopping": self.stopping,
        }

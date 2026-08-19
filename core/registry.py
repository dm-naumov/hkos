"""HKOS Registry
==============
Registry for internal HKOS components.
On DS-001, the Registry architecture exists but may be empty.
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class RegistryEntry:
    """An entry in the HKOS component registry."""

    name: str
    component: Any
    version: str = "0.0.0"
    description: str = ""


class Registry:
    """Internal component registry for HKOS.
    
    Allows HKOS subsystems to register themselves for discovery
    and lifecycle management. On DS-001, the architecture exists
    but may contain no entries.
    """

    def __init__(self) -> None:
        self._entries: dict[str, RegistryEntry] = {}

    def register(
        self,
        name: str,
        component: Any,
        version: str = "0.0.0",
        description: str = "",
    ) -> None:
        """Register a component in the registry."""
        self._entries[name] = RegistryEntry(
            name=name,
            component=component,
            version=version,
            description=description,
        )

    def unregister(self, name: str) -> None:
        """Remove a component from the registry."""
        self._entries.pop(name, None)

    def get(self, name: str) -> Any | None:
        """Get a registered component by name."""
        entry = self._entries.get(name)
        return entry.component if entry else None

    def contains(self, name: str) -> bool:
        """Check if a component is registered."""
        return name in self._entries

    def list(self) -> list[dict[str, Any]]:
        """List all registered components as dictionaries."""
        return [
            {
                "name": e.name,
                "version": e.version,
                "description": e.description,
            }
            for e in self._entries.values()
        ]

    @property
    def count(self) -> int:
        """Return the number of registered components."""
        return len(self._entries)

    @property
    def is_empty(self) -> bool:
        """Return True if no components are registered."""
        return len(self._entries) == 0

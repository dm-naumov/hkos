"""File-backed SnapshotPersistence port for the MCP server.

Канонический адрес класса — hkos.snapshot.file_persistence (DS-017 ЭТАП 5);
здесь — обратно совместимый shim-реэкспорт для mcp_server и его потребителей.
"""

from __future__ import annotations

from hkos.snapshot.file_persistence import FileSnapshotPersistence

__all__ = ["FileSnapshotPersistence"]

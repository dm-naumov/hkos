"""Minimal JSON-RPC 2.0 plumbing for the HKOS MCP server (stdlib only)."""

from __future__ import annotations

from typing import Any

JSONRPC_VERSION = "2.0"

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
APPLICATION_ERROR = -32000


def response(msg_id: int | str | None, result: Any) -> dict[str, Any]:
    """Build a JSON-RPC success response."""
    return {"jsonrpc": JSONRPC_VERSION, "id": msg_id, "result": result}


def error(
    msg_id: int | str | None,
    code: int,
    message: str,
    data: Any = None,
) -> dict[str, Any]:
    """Build a JSON-RPC error response."""
    payload: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        payload["data"] = data
    return {"jsonrpc": JSONRPC_VERSION, "id": msg_id, "error": payload}

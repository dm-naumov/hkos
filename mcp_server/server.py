"""HKOS MCP server: stdio JSON-RPC, zero runtime dependencies.

Protocol: MCP over stdio — newline-delimited JSON-RPC 2.0 messages.
Logging goes to stderr ONLY (stdout is the protocol channel).

Run:
    python -m hkos.mcp_server.server [--root DATA_ROOT] [--profile PROFILE]

Environment:
    HKOS_DATA_ROOT   data root (default ./hkos)
    HKOS_PROFILE     config profile (default production)
    HKOS_LOG_LEVEL   logging level for stderr (default WARNING)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from typing import Any

from hkos.core.exceptions import HKOSError
from hkos.core.version import VersionManager
from hkos.mcp_server.context import McpContext, build_context
from hkos.mcp_server.jsonrpc import (
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    error,
    response,
)
from hkos.mcp_server.tools import HANDLERS, TOOLS

_PROTOCOL_VERSION = "2024-11-05"
_LOGGER = logging.getLogger("hkos-mcp")


class McpServer:
    """Newline-delimited JSON-RPC 2.0 server over stdio (MCP transport)."""

    def __init__(self, data_root: str, profile: str) -> None:
        self._data_root = data_root
        self._profile = profile
        self._context: McpContext | None = None

    def _ctx(self) -> McpContext:
        if self._context is None:
            self._context = build_context(self._data_root, self._profile)
        return self._context

    def handle(self, message: dict[str, Any]) -> dict[str, Any] | None:
        """Handle one JSON-RPC message; None for notifications."""
        msg_id = message.get("id")
        method = message.get("method")
        if not isinstance(method, str):
            return error(msg_id, INVALID_REQUEST, "invalid request: missing method")
        params = message.get("params") or {}
        if not isinstance(params, dict):
            return error(msg_id, INVALID_PARAMS, "params must be an object")

        if method == "initialize":
            return response(msg_id, {
                "protocolVersion": _PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": "hkos-mcp",
                    "version": VersionManager().version_string,
                },
            })
        if method == "notifications/initialized":
            return None
        if method == "ping":
            return response(msg_id, {})
        if method == "tools/list":
            return response(msg_id, {"tools": TOOLS})
        if method == "tools/call":
            return self._call_tool(msg_id, params)
        return error(msg_id, METHOD_NOT_FOUND, f"method not found: {method}")

    def _call_tool(self, msg_id: int | str | None,
                   params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        if not isinstance(name, str):
            return error(msg_id, INVALID_PARAMS, "missing tool name")
        handler = HANDLERS.get(name)
        if handler is None:
            return error(msg_id, METHOD_NOT_FOUND, f"unknown tool: {name}")
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            return error(msg_id, INVALID_PARAMS, "arguments must be an object")
        missing = _missing_required(arguments, name)
        if missing is not None:
            return error(msg_id, INVALID_PARAMS,
                         f"missing required argument: {missing}")
        try:
            result = handler(self._ctx(), arguments)
        except HKOSError as exc:
            return _tool_result(msg_id, {"error": str(exc)}, is_error=True)
        except Exception as exc:  # noqa: BLE001 — process boundary: never crash
            _LOGGER.exception("tool %s failed", name)
            return _tool_result(msg_id, {"error": f"internal error: {exc}"},
                                is_error=True)
        return _tool_result(msg_id, result)


def _missing_required(arguments: dict[str, Any], name: str) -> str | None:
    """Return the first missing required argument, or None."""
    for tool in TOOLS:
        if tool["name"] != name:
            continue
        for key in tool["inputSchema"].get("required", []):
            if key not in arguments or arguments[key] in (None, ""):
                return str(key)
        return None
    return None


def _tool_result(msg_id: int | str | None, result: dict[str, Any],
                 is_error: bool = False) -> dict[str, Any]:
    """Wrap a tool result in the MCP content envelope."""
    text = json.dumps(result, ensure_ascii=False, default=str, indent=2)
    return response(msg_id, {
        "content": [{"type": "text", "text": text}],
        "isError": is_error,
    })


def main(argv: list[str] | None = None) -> int:
    """Stdio entry point (console script `hkos-mcp`)."""
    parser = argparse.ArgumentParser(
        prog="hkos-mcp", description="HKOS MCP server (stdio JSON-RPC)")
    parser.add_argument(
        "--root",
        default=os.environ.get("HKOS_DATA_ROOT", "./hkos"),
        help="HKOS data root (default: $HKOS_DATA_ROOT or ./hkos)")
    parser.add_argument(
        "--profile",
        default=os.environ.get("HKOS_PROFILE", "production"),
        help="config profile (default: production)")
    args = parser.parse_args(argv)

    logging.basicConfig(
        stream=sys.stderr,
        level=os.environ.get("HKOS_LOG_LEVEL", "WARNING"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    server = McpServer(args.root, args.profile)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            out = error(None, PARSE_ERROR, "parse error: invalid JSON")
            sys.stdout.write(json.dumps(out) + "\n")
            sys.stdout.flush()
            continue
        if not isinstance(message, dict):
            out = error(None, INVALID_REQUEST, "invalid request: not an object")
            sys.stdout.write(json.dumps(out) + "\n")
            sys.stdout.flush()
            continue
        reply: dict[str, Any] | None = server.handle(message)
        if reply is not None:
            sys.stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

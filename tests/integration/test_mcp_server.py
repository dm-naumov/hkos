"""Integration tests for the HKOS MCP server (stdio JSON-RPC).

Two layers:
1. Raw JSON-RPC client over the stdio transport (protocol-level contract).
2. Interop with the official MCP Python SDK client (skipped if not installed).
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PKG_PARENT = str(_REPO_ROOT.parent)


def _mcp_sdk_available() -> bool:
    try:
        import mcp  # noqa: F401
        return True
    except ImportError:
        return False


class McpClient:
    """Minimal stdio JSON-RPC client speaking to the hkos-mcp server."""

    def __init__(self, data_root: Path) -> None:
        env = {
            **os.environ,
            "PYTHONPATH": _PKG_PARENT,
            "HKOS_DATA_ROOT": str(data_root),
            "HKOS_LOG_LEVEL": "ERROR",
        }
        self._proc = subprocess.Popen(
            [sys.executable, "-m", "hkos.mcp_server.server", "--root", str(data_root)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            cwd=str(_REPO_ROOT),
        )
        self._seq = 0

    def send(self, method: str, params: dict[str, object] | None = None,
             notify: bool = False) -> Any:
        """Send one JSON-RPC message; return the response (None for notify)."""
        self._seq += 1
        message: dict[str, object] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        if not notify:
            message["id"] = self._seq
        assert self._proc.stdin is not None
        self._proc.stdin.write(json.dumps(message) + "\n")
        self._proc.stdin.flush()
        if notify:
            return None
        line = self._proc.stdout.readline() if self._proc.stdout else ""
        if not line:
            stderr = self._proc.stderr.read() if self._proc.stderr else ""
            raise RuntimeError(f"server closed stdout: {stderr[-2000:]}")
        result = json.loads(line)
        assert isinstance(result, dict)
        return result

    def call(self, tool: str,
             arguments: dict[str, object]) -> tuple[Any, bool]:
        """Call a tool; returns (decoded text result, is_error)."""
        resp = self.send("tools/call", {"name": tool, "arguments": arguments})
        assert resp is not None and "result" in resp
        result = resp["result"]
        assert isinstance(result, dict)
        content = result["content"]
        assert isinstance(content, list) and content
        text = content[0]["text"]
        assert isinstance(text, str)
        return json.loads(text), bool(result.get("isError", False))

    def close(self) -> None:
        if self._proc.stdin:
            self._proc.stdin.close()
        try:
            self._proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self._proc.kill()


class TestMcpServerProtocol:
    """Protocol contract: handshake, tool discovery, tool calls, errors."""

    def test_handshake_and_tool_list(self, tmp_path: Path) -> None:
        client = McpClient(tmp_path)
        try:
            init = client.send("initialize", {})
            assert init is not None and "result" in init
            info = init["result"]["serverInfo"]
            assert info["name"] == "hkos-mcp"
            assert info["version"] == "1.0.1"
            assert "tools" in init["result"]["capabilities"]

            client.send("notifications/initialized", {}, notify=True)

            tools = client.send("tools/list")
            assert tools is not None
            names = [t["name"] for t in tools["result"]["tools"]]
            assert names == ["retrieve", "context", "save",
                             "snapshot", "doctor", "status"]
        finally:
            client.close()

    def test_status_empty_root(self, tmp_path: Path) -> None:
        client = McpClient(tmp_path)
        try:
            status, is_error = client.call("status", {})
            assert not is_error
            assert status["ready"] is True
            assert status["version"] == "1.0.1"
            assert status["projects"] == 0
            assert status["knowledge_total"] == 0
        finally:
            client.close()

    def test_save_retrieve_snapshot_doctor_flow(self, tmp_path: Path) -> None:
        client = McpClient(tmp_path)
        try:
            saved, is_error = client.call("save", {
                "project": "Demo",
                "title": "TCP redirect works via nftables",
                "body": "meta l4proto tcp redirect to :12345",
                "tags": ["tcp", "nftables"],
                "kind": "fact",
            })
            assert not is_error
            assert saved["status"] == "CANONICAL"
            assert saved["category"] == "FACT"

            negative, is_error = client.call("save", {
                "project": "Demo",
                "title": "UDP bypasses the proxy",
                "body": "cause: tcp-only rule; fix: add tproxy rule",
                "kind": "negative",
            })
            assert not is_error
            assert negative["category"] == "FAILURE"  # classifier override

            result, is_error = client.call("retrieve", {
                "project": "Demo", "query": "udp proxy", "top_n": 5,
            })
            assert not is_error
            assert result["item_count"] >= 1
            first = result["items"][0]
            assert "explanation" in first and first["explanation"]["reason"]

            snapshot, is_error = client.call("snapshot", {
                "project": "Demo", "action": "create", "reason": "test",
            })
            assert not is_error
            assert snapshot["statistics"]["knowledge"] >= 2

            latest, is_error = client.call("snapshot", {
                "project": "Demo", "action": "latest",
            })
            assert not is_error and latest["snapshot_id"] == snapshot["snapshot_id"]

            report, is_error = client.call("doctor", {"project": "Demo"})
            assert not is_error
            assert report["verdict"] == "PASS"

            ctx, is_error = client.call("context", {
                "project": "Demo", "query": "udp proxy", "profile": "SMALL",
            })
            assert not is_error
            assert ctx["item_count"] >= 1
            assert "estimates" in ctx and "sections" in ctx
        finally:
            client.close()

    def test_error_cases(self, tmp_path: Path) -> None:
        client = McpClient(tmp_path)
        try:
            # Missing required argument
            resp = client.send("tools/call", {"name": "retrieve", "arguments": {}})
            assert resp is not None and resp["error"]["code"] == -32602

            # Unknown tool / method
            resp = client.send("tools/call", {"name": "nope", "arguments": {}})
            assert resp is not None and resp["error"]["code"] == -32601
            resp = client.send("bogus/method")
            assert resp is not None and resp["error"]["code"] == -32601

            # Unknown project -> tool error content (isError), not a crash
            _, is_error = client.call("retrieve",
                                      {"project": "Missing", "query": "x"})
            assert is_error is True

            # Malformed JSON -> parse error with null id
            assert client._proc.stdin is not None
            client._proc.stdin.write("{not json}\n")
            client._proc.stdin.flush()
            assert client._proc.stdout is not None
            resp = json.loads(client._proc.stdout.readline())
            assert resp["error"]["code"] == -32700
            assert resp["id"] is None
        finally:
            client.close()


@pytest.mark.skipif(not _mcp_sdk_available(),
                    reason="official MCP SDK not installed")
class TestMcpSdkInterop:
    """Interop with the official MCP Python SDK client (real client)."""

    def test_sdk_client_discovers_and_calls_tools(self, tmp_path: Path) -> None:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        from mcp.types import TextContent

        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "hkos.mcp_server.server", "--root", str(tmp_path)],
            env={**os.environ, "PYTHONPATH": _PKG_PARENT,
                 "HKOS_LOG_LEVEL": "ERROR"},
        )

        async def run() -> tuple[Any, list[str], str]:
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    init = await session.initialize()
                    tools = await session.list_tools()
                    await session.call_tool(
                        "save",
                        {"project": "SdkDemo",
                         "title": "SDK interop works",
                         "body": "end-to-end via official client",
                         "tags": ["sdk"]},
                    )
                    result = await session.call_tool(
                        "retrieve", {"project": "SdkDemo", "query": "sdk"})
                    first = result.content[0]
                    text = (first.text if isinstance(first, TextContent)
                            else "")
                    return (init, [t.name for t in tools.tools], text)

        init, names, text = asyncio.run(run())
        assert init.server_info.name == "hkos-mcp"
        assert {"retrieve", "context", "save", "snapshot",
                "doctor", "status"} <= set(names)
        assert "SDK interop works" in text

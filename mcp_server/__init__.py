"""HKOS MCP server adapter: stdio JSON-RPC server exposing HKOS tools to MCP clients.

Zero runtime dependencies. Run:

    python -m hkos.mcp_server.server [--root DATA_ROOT] [--profile PROFILE]

Environment: HKOS_DATA_ROOT (default ./hkos), HKOS_PROFILE (default production).
Console entry point: `hkos-mcp`.
"""

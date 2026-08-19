# HKOS MCP Server

HKOS speaks the **Model Context Protocol** over stdio — any MCP-capable
client (Claude Desktop, IDEs, agent frameworks) can retrieve from, write to
and inspect an HKOS knowledge base. The server is a **thin adapter**: it
marshals arguments and serializes results of existing public APIs, contains
zero business logic, and adds zero runtime dependencies.

## Architecture

```
MCP client (Claude Desktop / IDE / agent)
        │  stdio, newline-delimited JSON-RPC 2.0
        ▼
hkos.mcp_server.server ──► hkos.mcp_server.tools (6 tools)
        │                        │ thin adapters only
        ▼                        ▼
hkos.mcp_server.context  ──  public HKOS APIs
(file-backed SnapshotPersistence)   (Librarian, IndexEngine, RetrievalEngine,
                                    ContextBuilder, SnapshotEngine, HkosDoctor)
```

Design principles (same as the core system):

- **Zero daemon** — stdio transport, no background processes, no sockets.
- **Zero dependencies** — the server is stdlib-only JSON-RPC; the official
  `mcp` SDK is used only in tests to prove interop.
- **Deterministic** — no LLM anywhere in the server; results are exactly what
  the HKOS core produces.
- **Backward compatible** — a thin adapter; no HKOS API was changed to
  support MCP.

## Tools

| Tool | Purpose | Core API behind it |
|---|---|---|
| `retrieve` | deterministic ranked retrieval with explanations | RetrievalEngine |
| `context` | budgeted context document (sections + token estimates) | RetrievalEngine + ContextBuilder |
| `save` | write knowledge through the only write path | Librarian + IndexEngine |
| `snapshot` | create/read versioned snapshots | SnapshotEngine |
| `doctor` | consistency check (repository vs index vs snapshot) | HkosDoctor |
| `status` | version, data root, corpus size | VersionManager + repositories |

Every tool returns JSON in the MCP text content envelope. Errors are returned
as `isError: true` content (or JSON-RPC errors for protocol-level problems).

## Running

```bash
pip install hkos            # ships the hkos-mcp console command
hkos-mcp --root ./hkos      # HKOS_DATA_ROOT / HKOS_PROFILE env vars also work
```

The server reads newline-delimited JSON-RPC from stdin and writes responses
to stdout. Logs go to stderr only.

## Claude Desktop configuration

`claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "hkos": {
      "command": "hkos-mcp",
      "args": ["--root", "/absolute/path/to/data/root"],
      "env": { "HKOS_PROFILE": "production" }
    }
  }
}
```

Any other MCP client works the same way: point it at `hkos-mcp`.

## Example session

```
user:  hkos retrieve  {"query": "udp proxy", "project": "OpenWrt"}

assistant tool result:
{
  "project_id": "4d1aafd1-...",
  "item_count": 3,
  "items": [
    {
      "id": "0282df6f-...",
      "type": "knowledge",
      "title": "UDP bypasses the proxy",
      "status": "CANONICAL",
      "confidence": 95,
      "explanation": { "reason": "keyword match (proxy)", "score": 0.9, ... }
    },
    ...
  ]
}
```

## Verification

- `tests/integration/test_mcp_server.py` — protocol contract tests (raw
  JSON-RPC client) and interop tests against the **official MCP Python SDK**
  (real `ClientSession` over stdio).
- Perf: tool calls add single-digit-millisecond overhead over the core APIs
  (measured in the same test run); the server is a synchronous adapter.

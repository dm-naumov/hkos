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

## `save` tool: typed links (`relations`) and warnings

`save` accepts an optional `relations` array to link the new knowledge item to
existing entities (DS-017 §4.2.1, IP-017 ЭТАП 2):

```json
{
  "project": "OpenWrt",
  "title": "UDP bypasses the proxy",
  "relations": [
    {"target_id": "<existing-entity-id>", "relation_type": "BASED_ON"},
    {"target_id": "<decision-id>", "relation_type": "CAUSED_BY",
     "target_project_id": "<other-project-id>"}
  ]
}
```

Element fields: `target_id` (required), `relation_type` (required — one of the
`RelationType` values, e.g. `BASED_ON`, `CAUSED_BY`, `MITIGATED_BY`,
`REFERENCE_TO`, `DERIVED_FROM`), `target_project_id` (optional — cross-project
target; empty = same project).

Validation (deterministic, in the Librarian — the only write path):

- the target must exist in the target project (knowledge/decision/artifact/
  campaign entities are valid targets);
- an explicit `target_project_id` must point to an existing project;
- self-loops are rejected;
- unknown `relation_type`, missing `target_id` or malformed elements are
  rejected at the adapter layer.

Invalid links are **dropped with reasons** — they never fail the whole save and
are never persisted silently. The response always carries a `warnings` array:

```json
{ "id": "...", "project_id": "...", "category": "...", "status": "...",
  "warnings": ["relations[2]: unknown relation_type 'TELEPORT'",
               "relation target bogus-id: target not found in project ..."] }
```

Direct Python API callers get the same guarantees through
`Librarian.validate_relations(project_id, source_id, relations)` (soft path,
returns valid relations + reasons) and through `register`/`update`, which raise
`LibrarianError` on invalid relations (strict backstop).

### Category suggestion transparency (DS-017 §4.3.1)

`save` accepts a `category` hint, but the deterministic classifier in the
Librarian always decides the final category (`register` ignores a pre-set
`knowledge.category`; only the explicit `category` parameter of
`register`/`update` wins). Classification rules, in order:

1. `kind = "negative"` → `FAILURE` (`rule:kind:negative`);
2. keyword markers in title/body → category (`rule:marker:<CATEGORY>`);
3. otherwise → `FACT` (`rule:default:fact`).

If the agent's hint is overridden or invalid, the response `warnings` carries
the reason with the id of the rule that fired:

```json
{ "id": "...", "category": "FAILURE", "warnings": [
    "category overridden: suggested 'SUCCESS' classified as 'FAILURE' (rule: rule:kind:negative)"] }
```

A matching hint (or no hint) produces no category warning. The same decision
for an unsaved knowledge item is available through
`Librarian.explain_category(knowledge) -> (category, rule_id)` and
`KnowledgeClassifier.classify_with_rule(knowledge)`.

### IDE presets

Ready-to-copy MCP configs ship in `examples/`:

- **Cursor** — `examples/cursor-mcp.json` (place as `.cursor/mcp.json`);
- **Windsurf** — `examples/windsurf-mcp.json` (place as `mcp_config.json`);
- Claude Desktop — see the config above.

All presets run `uvx hkos-mcp` and take the data root from the
`HKOS_DATA_ROOT` environment variable — set it to an absolute path before
first use. Framework wiring (LangChain / AutoGen) is in
`examples/integrations.md`.

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

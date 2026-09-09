# ADR-001 amendment: KI-003 MCP observation write path

## Status

Accepted. This amendment supersedes the KI-003 deviation status in
`adr-001-knowledge-integrity-contract.md`.

## Resolution

The MCP `save` tool records and indexes a `NEW` observation when
`canonicalize` is omitted or false. Ordinary retrieval remains
`CANONICAL`-only, while explicit history retrieval may inspect the indexed
observation.

`canonicalize=true` remains an explicit elevated compatibility action in this
stage. Removing the implicit `NEW -> VERIFIED -> CANONICAL` transition belongs
to KI-004 and is intentionally out of scope.

## Compatibility

This default flip is intentional. Clients that require immediate canonical
knowledge must explicitly pass `canonicalize=true` until the KI-004 lifecycle
API replaces this compatibility action with separate verification and
canonicalization steps.

## Verification

Regression coverage lives in:

- `tests/architecture/test_knowledge_integrity_contract.py`;
- `tests/integration/test_knowledge_integrity_baseline.py`;
- `tests/integration/test_mcp_server.py`.

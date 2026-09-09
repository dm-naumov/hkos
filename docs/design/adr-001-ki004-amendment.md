# ADR-001 amendment: KI-004 explicit verification lifecycle

## Status

Accepted. This amendment resolves KI-004 and supersedes its deviation status
in `adr-001-knowledge-integrity-contract.md`.

## Resolution

Trust promotion consists of two separate public Librarian operations:

1. `verify(project_id, knowledge_id)` performs `NEW -> VERIFIED` and appends
   the `Verified` history event;
2. `canonicalize(project_id, knowledge_id)` performs
   `VERIFIED -> CANONICAL` and appends `Canonicalized`.

`canonicalize` no longer performs an implicit verification transition. Calling
it for `NEW` raises `KnowledgeStatusError` through the existing lifecycle state
machine.

## Idempotence

- `verify` is a no-op for `VERIFIED` and `CANONICAL` knowledge;
- `canonicalize` is a no-op for `CANONICAL` knowledge.

No history event is appended for an idempotent no-op.

## Compatibility

The explicit MCP compatibility action `canonicalize=true` now invokes
`verify` and `canonicalize` in sequence, preserving its promoted result while
recording both domain actions. Ordinary MCP saves remain `NEW`.

Trusted fixtures, examples and integrations must call `verify` before
`canonicalize`. Direct `NEW -> CANONICAL` is no longer supported.

## Non-goals

KI-006 remains separate: this stage does not remove repository-level archive
mutation APIs.

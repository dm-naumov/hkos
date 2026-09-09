# Explicit verification lifecycle

KI-004 separates trust promotion into two public, auditable actions:

1. `register(...)` creates `NEW`;
2. `verify(...)` performs `NEW -> VERIFIED` and records `Verified`;
3. `canonicalize(...)` performs `VERIFIED -> CANONICAL` and records `Canonicalized`.

Calling `canonicalize(...)` for `NEW` now raises `KnowledgeStatusError`. Both
`verify` on already verified/canonical knowledge and `canonicalize` on already
canonical knowledge are idempotent.

The MCP `canonicalize=true` compatibility action invokes both public actions
explicitly. Ordinary MCP saves remain `NEW` as established by KI-003.

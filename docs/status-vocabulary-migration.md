# Knowledge status vocabulary migration

HKOS uses one canonical lifecycle vocabulary for Knowledge:

`NEW`, `VERIFIED`, `CANONICAL`, `SUPERSEDED`, `CONFLICT`, `REJECTED`,
`ARCHIVED`.

## Compatibility behavior

Existing v1.x JSON Repository documents are migrated lazily at the read
boundary. Their files are not rewritten merely by reading them. A later
successful save writes the normalized uppercase status.

Legacy pre-validation states are mapped conservatively:

- `new`, `candidate`, `under_review` → `NEW`;
- `validated`, `verified` → `VERIFIED`;
- lowercase canonical names map to their uppercase equivalent.

This policy never manufactures verification from `under_review`. Unknown
values remain visible to validation on read and are rejected on write.

The legacy compatibility constant names `KNOWLEDGE_STATUS_CANDIDATE`,
`KNOWLEDGE_STATUS_UNDER_REVIEW`, and `KNOWLEDGE_STATUS_VALIDATED` remain as
1.x import aliases. They do not add lifecycle states.

This change resolves ADR-001 deviations KI-005 and KI-009. It does not change
default retrieval eligibility, graph eligibility, MCP save defaults,
canonicalization flow, or the Repository archive API.

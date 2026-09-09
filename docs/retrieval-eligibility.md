# Retrieval eligibility

Ordinary HKOS retrieval uses a positive eligibility rule:

```text
Knowledge is eligible if and only if status == CANONICAL
```

`include_history=True` is an explicit diagnostic/history policy and may return
non-canonical Knowledge. Entity types outside the Knowledge lifecycle are not
subject to this status rule.

Relationship traversal is only a candidate source. After expansion, every
relation-added candidate passes the same eligibility policy as direct
candidates, so a graph edge cannot expose NEW, VERIFIED, CONFLICT, REJECTED,
SUPERSEDED, or ARCHIVED Knowledge in ordinary results.

This change resolves ADR-001 deviations KI-001 and KI-002. It does not change
MCP save defaults, lifecycle transitions, Repository write boundaries,
snapshot diff semantics, or revision/CAS behavior.

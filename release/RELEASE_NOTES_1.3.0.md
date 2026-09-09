# HKOS v1.3.0 Release Notes — Knowledge Integrity contract

**Date:** 2026-09-10
**Contract:** ADR-001 Knowledge Integrity (KI-001…KI-009)
**Backward compatibility:** drop-in replacement for v1.2.x; no storage
migration required — existing JSON repositories are fully compatible.

## Headline

This release fully implements the **Knowledge Integrity contract**
([ADR-001](../docs/design/adr-001-knowledge-integrity-contract.md)),
resolving all nine deviations (KI-001…KI-009) that were tracked as
executable XFAIL contracts since v1.2.

## Changes

- **KI-002** — Removed the double eligibility filter in
  `Retriever.run_parsed`: traversal now starts from the full ranked set;
  `KnowledgeFilter` is applied exactly once on the expanded result.
  Non-canonical items can now seed relation paths that lead to canonical
  knowledge.
- **KI-004** — Explicit verification lifecycle: `verify()` is a required step
  before `canonicalize()`; the Librarian enforces NEW → VERIFIED → CANONICAL.
- **KI-006** — Removed the legacy `KnowledgeRepository.archive()`; archiving
  is exclusively a Librarian operation, reinforcing the single write-path
  invariant.
- **KI-007** — Fixed snapshot diff: `body` is now included in section
  indexing, so body changes are correctly detected and reported.
- **KI-008** — Concurrency-safe repository writes: `_rev` revision counter in
  every envelope, `expected_revision` check in `update()`,
  `RepositoryConcurrencyError` on conflict.
- **KI-001, KI-003, KI-005, KI-009** — resolved in prior patch commits.

## Integrity contract status

All XFAIL deviation contracts are now green. The lifecycle diagram in the
README reflects the fully implemented contract.

## Upgrading

Drop-in replacement for v1.2.x. No storage migration required; existing JSON
repositories are fully compatible.

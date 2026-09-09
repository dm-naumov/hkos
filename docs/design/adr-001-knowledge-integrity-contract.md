# ADR-001: Knowledge Integrity Contract

## Status

Accepted as target contract; implementation is incremental. v1.2.0 deviates
from several clauses — every deviation is enumerated in "Known deviations
in v1.2.0" with a KI-ID, a regression test reference and a planned
remediation stage. This document is the normative basis for the lifecycle,
retrieval and MCP write-path follow-up tasks.

## Context

HKOS stores engineering knowledge as JSON documents (repository = SSOT)
and exposes it to agents through deterministic retrieval (Query Contract
Q1–Q5), graph traversal over typed relations, snapshots and an MCP server.
The lifecycle vocabulary, retrieval eligibility and the MCP write path
grew incrementally across DS-006/DS-008/DS-016/DS-017. A code audit of
v1.2.0 shows that:

- ordinary retrieval keeps NEW/VERIFIED/CONFLICT candidates
  (`retrieval/knowledge_filter.py`);
- graph traversal expands candidates *after* the eligibility filter and
  does not re-check added neighbors (`retrieval/retriever.py`,
  `retrieval/relationship_traverser.py`);
- MCP `save` canonicalizes by default (`canonicalize: true`), turning an
  agent observation into CANONICAL in one call;
- `Librarian.canonicalize` performs an implicit NEW → VERIFIED → CANONICAL
  hop with no separate public verification action;
- two status vocabularies coexist (`repository/models.py` lowercase
  legacy vs `services/librarian/knowledge_status.py` uppercase), and
  `KnowledgeRepository.archive()` mutates lifecycle status directly.

This ADR fixes the *target* integrity contract that those follow-up tasks
implement one deviation at a time. It does not describe v1.2.0 behavior as
current except where explicitly labelled.

## Decision

1. Adopt the invariant set below (§ Invariants) as non-negotiable
   architectural constraints of HKOS.
2. Adopt the default retrieval eligibility rule (§ Default retrieval
   eligibility): ordinary retrieval and ordinary agent context admit only
   status `CANONICAL`; everything else requires an explicit, named policy
   (history/diagnostic/review) that never silently mixes into ordinary
   agent context.
3. Adopt the graph eligibility rule (§ Graph traversal eligibility):
   graph expansion is a candidate *source*, not an eligibility bypass.
4. Adopt the observation/verification/canonicalization separation
   (§ Observation, verification and canonicalization) and the single
   status vocabulary (§ Status vocabulary).
5. Revision, temporal and provenance semantics are planned additive
   extensions (§ Revision and temporal semantics, § Provenance and
   explanations); their reader-facing shape is frozen here so later schema
   evolution stays backward compatible (§ Compatibility and migration
   policy).
6. Semantic retrieval is a future optional candidate provider bounded by
   § Semantic retrieval boundary; the frozen Query Contract is not
   extended with a new query.
7. Roll out per § Rollout sequence: characterization first (this
   baseline), then one deviation per implementation task.

## Terminology

- **Repository / SSOT**: the JSON knowledge documents under `projects/`;
  canonical data, the single source of truth.
- **Derived projection**: anything rebuildable from the repository —
  indexes (JSON `*.idx` or SQLite `index_store.db`), snapshots, manifests,
  caches.
- **Knowledge**: an engineering claim stored via the repository; has a
  lifecycle `status`, a history of workflow events, and typed `relations`.
- **Status**: lifecycle state of a Knowledge document (single vocabulary,
  § Status vocabulary).
- **Eligibility**: the predicate that decides whether a knowledge item may
  appear in ordinary retrieval / ordinary agent context.
- **Observation / claim**: an unverified agent-recorded statement. Enters
  the system as `NEW`.
- **Verification**: a distinct, accountable action confirming a claim
  (`NEW → VERIFIED`).
- **Canonicalization**: a distinct, accountable action promoting a
  verified claim (`VERIFIED → CANONICAL`).
- **Ordinary agent context**: the default context assembled for a regular
  agent task (retrieval default policy, no explicit history/review flags).
- **Provenance**: recorded facts about where a knowledge item came from
  and how it changed (repository-level).
- **Explanation**: the deterministic account of why a candidate was
  retrieved and ranked (retrieval-level).

## Invariants

1. **Repository = SSOT.** `projects/` knowledge documents are canonical;
   every backend and derived layer is subordinate to them.
2. **One repository semantics.** JSON and future repository backends
   implement the same repository contract; switching a backend never
   changes knowledge semantics.
3. **Indexes, SQLite index store, snapshots, manifests and caches are
   derived projections.**
4. **Derived projections are rebuildable.** Any index/snapshot/cache can
   be regenerated from the repository without data loss.
5. **Librarian is the only business write path for Knowledge.** Status
   transitions and domain mutations go through Librarian operations.
6. **Retrieval never touches the filesystem, StorageEngine, JSON or
   IndexStore directly** — enforced by architecture tests.
7. **Retrieval uses Query Contract Q1–Q5 and the repository only by
   selected UUID.**
8. **Query Contract Q1–Q5 is frozen.**
9. **Semantic retrieval, when added, is an optional candidate provider,
   never a source of truth.**
10. **No built-in LLM participates in canonicalization, eligibility or
    truth policy.**
11. **The deterministic core stays fully usable without any semantic
    backend.**
12. **Ordinary agent context contains no unresolved lifecycle-policy
    knowledge** (non-canonical items require explicit policies).
13. **Graph traversal cannot bypass eligibility.**
14. **Observation does not automatically become canonical knowledge.**
15. **Verification and canonicalization are distinct domain actions.**
16. **Lifecycle status, temporal validity and revision history are
    distinct concepts.**
17. **Retrieval explanation and knowledge provenance are distinct levels
    of explanation.**
18. **Schema evolution requires a backward-compatible reader and an
    explicit migration strategy.**

## Default retrieval eligibility

Rule (positive form, no "exclude these statuses" model):

    ordinary retrieval eligibility(status) == (status == CANONICAL)

Implementation requirements:

- The default candidate filter must *admit* `CANONICAL` explicitly rather
  than *exclude* a denylist (`status not in {ARCHIVED, REJECTED,
  SUPERSEDED}` is rejected as the default model).
- `NEW`, `VERIFIED`, `CONFLICT`, `REJECTED`, `ARCHIVED`, `SUPERSEDED` are
  not eligible for ordinary agent context.
- Historical, diagnostic and review queries may use other policies, but
  each such policy is explicit (e.g. `include_history`, a review flag) and
  the result is never silently mixed into ordinary agent context.
- The eligibility predicate is applied to every candidate that may reach
  the ordinary result, regardless of how the candidate was obtained.

## Graph traversal eligibility

- A candidate added through a relation is a candidate like any other: it
  must satisfy the same eligibility policy as a direct candidate.
- A graph relation can never make a `NEW`, `CONFLICT`, `REJECTED`,
  `ARCHIVED` or `SUPERSEDED` item eligible for ordinary context.
- If expansion introduces items that are not eligible, those items are
  either dropped from the ordinary result or surfaced under an explicit
  non-ordinary policy; they never appear in ordinary agent context.
- Traversal remains deterministic BFS over Q4 with depth/volume bounds;
  eligibility is applied per added candidate (same predicate, same code
  path as direct candidates).

## Observation, verification and canonicalization

- **Observation**: an agent write is an observation/claim and initially
  receives status `NEW`.
- **Default write path**: agent saves do not by default perform
  `NEW → VERIFIED → CANONICAL`; promotion requires explicit actions.
- **Verification** is a separate action: `NEW → VERIFIED`. In the future
  it records actor, timestamp, reason and a policy/evidence reference.
- **Canonicalization** is a separate action: `VERIFIED → CANONICAL`.
  Direct public `NEW → CANONICAL` is not part of the target contract.
- MCP/API: a plain `save` (no elevated action) returns a `NEW` item;
  canonicalization requires an explicit `verify`/`canonicalize` action.

## Status vocabulary

One authoritative vocabulary (uppercase), defined once:

    NEW, VERIFIED, CANONICAL, SUPERSEDED, CONFLICT, REJECTED, ARCHIVED

- All modules import these names from a single definitions module.
- Lowercase legacy values are tolerated only through backward-compatible
  normalization/migration at the read boundary, never as a second domain
  vocabulary and never stored by current write paths.
- Repository-level persistence must not introduce lifecycle mutations or
  status constants of its own (see KI-005, KI-006).

## Revision and temporal semantics

The following concepts are distinct and planned as additive extensions;
this ADR fixes their meaning, not their v1.x implementation:

- `revision` — per-entity revision counter (optimistic concurrency);
- `observed_at` — when the fact was observed;
- `recorded_at` — when the observation entered the repository;
- `verified_at` — when verification happened;
- `valid_from`, `valid_until` — temporal validity window;
- `superseded_at` — when a canonical item was superseded.

Lifecycle `status`, `revision`, temporal validity and the workflow
`history` are different concepts and must not be conflated in the model or
in retrieval semantics.

## Provenance and explanations

- **Knowledge provenance** (repository level): origin, actors, policy
  references, evidence references, history of lifecycle events.
- **Retrieval explanation** (retrieval level): deterministic account of
  *why a candidate was retrieved and ranked* — matched keywords/topic,
  score factors, relation path.
- These are two different levels; an explanation never masquerades as
  provenance and vice versa. `why_retrieved` (ranking factors) is
  distinguished from `why_trusted` (verification/canonicalization/provenance
  evidence).

## Semantic retrieval boundary

A future semantic backend:

- may *propose* candidates and provide a *semantic relevance signal* that
  feeds the deterministic pipeline;
- may not make an item CANONICAL;
- may not bypass eligibility;
- may not replace the repository as SSOT;
- is never required for the deterministic core to function.

The frozen Query Contract Q1–Q5 is not extended (no Q6) for semantic
retrieval; semantic signals arrive through the existing candidate
interface only.

## Compatibility and migration policy

- All schema additions are additive: old readers keep working, new fields
  carry defaults.
- Any new field documented here (revision, observed_at, verified_at,
  valid_from/until, superseded_at, evidence references) lands with a
  backward-compatible reader and an explicit migration strategy.
- The envelope `version` is the document-envelope format version, not a
  content revision; content revisions are introduced explicitly under the
  `revision` concept.

## Known deviations in v1.2.0

Each deviation is confirmed against v1.2.0 source. Characterization tests
live in `tests/integration/test_knowledge_integrity_baseline.py`; the
executable target contract lives in
`tests/architecture/test_knowledge_integrity_contract.py` (strict XFAIL
keyed by KI-ID until fixed).

### KI-001 — Default eligibility is a denylist, not `CANONICAL`-only

- Affected files: `retrieval/knowledge_filter.py`,
  `retrieval/retriever.py`.
- Observed current behavior: default filter excludes only ARCHIVED,
  REJECTED, SUPERSEDED; NEW, VERIFIED, CANONICAL and CONFLICT pass into
  ordinary retrieval (docstring and code: `status not in {ARCHIVED,
  REJECTED, SUPERSEDED}`).
- Target behavior: ordinary eligibility admits CANONICAL only.
- Risk: NEW claims, unresolved conflicts and unverified items surface in
  ordinary agent context.
- Planned remediation stage: retrieval eligibility task (next).
- Required regression test:
  `tests/architecture/test_knowledge_integrity_contract.py`
  (`TestDefaultEligibility`, XFAIL KI-001).

### KI-002 — Graph expansion bypasses eligibility

- Affected files: `retrieval/retriever.py` (pipeline order: filter at step
  4, traverse at step 5),
  `retrieval/relationship_traverser.py`.
- Observed current behavior: `RelationshipTraverser.traverse` runs after
  `KnowledgeFilter`; neighbors added via relations are appended without a
  second eligibility pass. An ARCHIVED neighbor of a CANONICAL anchor is
  returned by ordinary retrieval (characterization
  `TestGraphTraversalCurrent`).
- Target behavior: every relation-added candidate passes the same
  eligibility policy as direct candidates.
- Risk: archived/rejected/superseded knowledge leaks into ordinary agent
  context through the graph.
- Planned remediation stage: retrieval eligibility task (same as KI-001).
- Required regression test:
  `tests/architecture/test_knowledge_integrity_contract.py`
  (`TestGraphEligibility`, XFAIL KI-002).

### KI-003 — MCP save canonicalizes by default

- Affected files: `mcp_server/tools.py` (save schema `canonicalize:
  {type: boolean, default: true}`; handler calls `Librarian.canonicalize`
  right after `register` when `args.get("canonicalize", True)`).
- Observed current behavior: a plain agent save becomes CANONICAL
  (characterization `TestMcpSaveCurrent`); schema default is true.
- Target behavior: a plain save (observation) stays NEW; canonicalization
  requires an explicit elevated action.
- Risk: agent claims are recorded as canonical truth without verification.
- Planned remediation stage: MCP write-path task.
- Required regression test:
  `tests/architecture/test_knowledge_integrity_contract.py`
  (`TestObservationAndCanonicalization::test_save_without_elevated_action_not_canonical`,
  XFAIL KI-003).

### KI-004 — canonicalize() silently hops NEW → VERIFIED → CANONICAL

- Affected files: `services/librarian/librarian.py` (`canonicalize`).
- Observed current behavior: canonicalizing a NEW knowledge performs an
  internal `_transition(VERIFIED)` then `_transition(CANONICAL)` in one
  public call; history records only Created + Canonicalized (no separate
  verification event) — characterization
  `test_history_after_canonicalize_new`.
- Target behavior: canonicalization is `VERIFIED → CANONICAL`; promotion
  of NEW requires a separate public verify action; direct public
  NEW → CANONICAL is out of contract.
- Risk: verification is skipped without a traceable event.
- Planned remediation stage: lifecycle task.
- Required regression test:
  `tests/architecture/test_knowledge_integrity_contract.py`
  (`test_new_cannot_be_canonicalized_without_verify`, XFAIL KI-004).

### KI-005 — Two status vocabularies (lowercase legacy vs uppercase)

- Affected files: `repository/models.py` (KNOWLEDGE_STATUS_NEW = "new",
  plus CANDIDATE/UNDER_REVIEW/VALIDATED/CANONICAL/SUPERSEDED/ARCHIVED,
  lowercase), `repository/knowledge_repository.py` (imports lowercase
  constants, parse default `status="new"`),
  `services/librarian/knowledge_status.py` (uppercase NEW/VERIFIED/
  CANONICAL/SUPERSEDED/CONFLICT/REJECTED/ARCHIVED).
- Observed current behavior: two modules define different vocabularies —
  differing value case and differing state sets (candidate/under_review/
  validated exist only in the lowercase set; VERIFIED/CONFLICT/REJECTED
  exist only in the uppercase set). Knowledge defaults to lowercase
  "new" at the model layer while Librarian writes uppercase "NEW".
- Target behavior: one authoritative uppercase vocabulary; legacy
  lowercase handled only via backward-compatible normalization at the
  read boundary.
- Risk: status comparisons silently fail across layers (e.g. a lowercase
  "archived" record would not be excluded by the uppercase denylist —
  retrieval leak), and repository-level constants invite direct mutation.
- Planned remediation stage: lifecycle/vocabulary task (consolidation plus
  read-boundary normalization).
- Required regression test:
  `tests/architecture/test_knowledge_integrity_contract.py`
  (`TestStatusVocabulary`, XFAIL KI-005).

### KI-006 — Repository exposes a lifecycle mutation (archive)

- Affected files: `repository/knowledge_repository.py` (`archive()`),
  `repository/base_repository.py`.
- Observed current behavior: `KnowledgeRepository.archive(project, id)`
  sets the status directly to the repository-level (lowercase) ARCHIVED
  constant, bypassing Librarian policy and the uppercase vocabulary.
- Target behavior: the repository layer exposes no lifecycle mutations;
  status changes happen only through Librarian operations.
- Risk: policy bypass (no transition validation, no history event,
  vocabulary mismatch) via the persistence API.
- Planned remediation stage: lifecycle task.
- Required regression test:
  `tests/architecture/test_knowledge_integrity_contract.py`
  (`TestRepositoryBoundary`, XFAIL KI-006).

### KI-007 — Snapshot diff is not a content diff

- Affected files: `snapshot/snapshot_diff.py`.
- Observed current behavior: diff compares entries by `id` and `title`
  per section (`_section_index` maps id → {title, section}); body/content
  changes inside a kept entry are not reported as changes.
- Target behavior: snapshot diff semantics are explicitly defined
  (either content-aware diff, or documented as an identity/title-level
  delta with a distinct name); no silent claim of full content diff.
- Risk: users rely on diff for content change detection and miss edits.
- Planned remediation stage: snapshot semantics task.
- Required regression test: pending — see "Planned executable contracts".

### KI-008 — No entity revision / optimistic concurrency

- Affected files: `repository/base_repository.py` (`_envelope`),
  `repository/json_store.py` (envelope version), `repository/models.py`
  (no revision field).
- Observed current behavior: the envelope `version` is preserved on update
  (`doc[KEY_VERSION] = existing.get(KEY_VERSION, ...)`) and is not
  incremented per content change — it is a document-envelope format
  marker, not a content revision. Knowledge has no revision counter;
  concurrent updates overwrite silently (last write wins).
- Target behavior: a per-entity `revision` (optimistic concurrency) is a
  planned additive extension; envelope version stays the format marker.
- Risk: lost updates under concurrent writers; no way to detect stale
  edits.
- Planned remediation stage: revision/temporal semantics task.
- Required regression test: pending — see "Planned executable contracts".

### Additional observed deviations

**KI-009 — Case-sensitive status comparisons leak legacy lowercase data
through eligibility.** Because the filter compares against uppercase
constants and repository parsing defaults missing status to lowercase
"new", any record carrying a lowercase status (legacy or imported) is
neither excluded nor normalized by current read paths; e.g. a lowercase
"archived" item passes the default filter. Root cause is KI-005; tracked
separately because the observable defect is in the eligibility path.
Affected files: `retrieval/knowledge_filter.py`,
`repository/knowledge_repository.py`. Planned remediation: with KI-005
(read-boundary normalization). No separate test added — covered by the
KI-005 vocabulary consolidation and its read-boundary normalization test.

## Consequences

- Follow-up implementation tasks are strictly sequenced per KI-ID (see
  Rollout sequence) and each must remove exactly one XFAIL marker.
- Behavior changes land behind the existing public APIs; the MCP schema
  default flip (KI-003) is a deliberate breaking change for clients that
  rely on save-to-CANONICAL and is rolled out with release notes.
- The deterministic core, repository semantics and the frozen Query
  Contract are untouched by the whole remediation programme.
- Characterization tests in
  `tests/integration/test_knowledge_integrity_baseline.py` stay as the
  "before" record; they are updated (not deleted) as behavior changes.

## Rollout sequence

1. This baseline (ADR + characterization + executable contract tests) —
   no production change. (Current task.)
2. Retrieval eligibility: KI-001 + KI-002 (single pass: default policy
   CANONICAL-only, graph candidates re-checked).
3. Lifecycle: KI-004 + KI-006 (+ KI-005 vocabulary consolidation and
   read-boundary normalization; KI-009 rides with it).
4. MCP write path: KI-003 (explicit elevated action; default stays NEW).
5. Snapshot semantics: KI-007.
6. Revision/temporal semantics: KI-008 (additive fields with
   backward-compatible reader + migration).

## Test strategy

- **Characterization** (`tests/integration/test_knowledge_integrity_baseline.py`):
  pins v1.2.0 behavior through public components (Librarian, filter, MCP
  server, retrieval) — green today, updated as deviations are fixed.
- **Executable contract** (`tests/architecture/test_knowledge_integrity_contract.py`):
  expresses the target contract; unsatisfied clauses are strict XFAIL with
  the KI-ID in the reason; removing a marker is the definition of done for
  the corresponding remediation task.
- Deviations without an executable test yet (KI-007, KI-008) are listed in
  "Planned executable contracts" below and get tests once the production
  API exists; no artificial tests were added that would require new
  production API.

### Planned executable contracts

- KI-007: content-diff contract test (requires a defined content-diff or a
  renamed identity-delta API).
- KI-008: revision monotonicity and optimistic-concurrency contract test
  (requires the `revision` field on the entity model).

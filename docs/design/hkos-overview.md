# HKOS Design Overview

A short summary of the fundamental design decisions behind HKOS and the
reasoning for each. The full specification (HKOS-02…HKOS-16) is maintained
privately; this document covers the public reasoning.

## 1. The repository is the single source of truth (SSOT)

**Decision:** All knowledge, decisions, projects and campaigns live in a plain
JSON repository. Indexes, snapshots, manifests and caches are *derived
projections* — rebuildable from the repository at any time.

**Why:** In agent memory systems, the "memory" is often a vector index whose
contents cannot be reconstructed from anything else. If the index is lost or
corrupted, the memory is gone. With an SSOT, corruption of any derived
artifact is a rebuild away. It also makes the memory human-auditable: the
repository is readable JSON.

**Trade-off:** reads that could hit a cache must go through the repository for
authority; some operations cost an O(index) parse on first access. Mitigated
by IndexCache (warm ≈0.03 ms).

## 2. Deterministic classification — no LLM in the write path

**Decision:** Knowledge categories (FACT, DECISION, FAILURE, CONFIGURATION,
RULE, …) are assigned by a rule-based classifier. LLMs are never consulted
when writing, classifying, indexing or retrieving knowledge.

**Why:** LLM-dependent memory changes behavior when the model changes, is
probabilistic, and is not auditable. Deterministic classification means the
same input always produces the same memory state — a hard requirement for
engineering knowledge.

**Trade-off:** the classifier cannot understand nuance an LLM would. This is
accepted: ambiguity is resolved toward the safe category, and the knowledge
body keeps the full human/agent-written text.

## 3. Negative knowledge is a first-class citizen

**Decision:** FAILURE entries (with cause/fix) are stored like any other
knowledge and ranked *first* when a similar problem is queried.

**Why:** the highest-value engineering memory is "what broke and how we fixed
it". Retrieval that surfaces past failures before repeating them turns memory
into a safety mechanism, not just a lookup.

## 4. File-based storage, no daemon

**Decision:** HKOS is a library. Everything is files (JSON envelopes,
HKOS-08); there is no server, no daemon, no hidden database.

**Why:** zero operational footprint, trivially backupable/restorable (a
directory copy), diffable, and process-independent — memory survives the
process that wrote it.

## 5. Crash-safe by construction

**Decision:** all writes are atomic (write to tmp + rename). A `kill -9`
mid-write leaves either the old or the new record, never a partial one.

**Why:** agent processes die unexpectedly. Memory corruption on crash is
unacceptable for a system whose purpose is reliability.

## 6. Schema evolution is a designed feature

**Decision:** a migration engine with a single-use FSM
(backup → apply → rebuild index → regenerate snapshot → validate), an
append-only event log, a stale-aware lock, and idempotent rollback.

**Why:** knowledge bases outlive their schema. Migrations that can be rolled
back without data loss are what makes a long-lived memory system trustworthy.

## 7. Deterministic, explainable retrieval

**Decision:** retrieval is a fixed pipeline (query → parser → builder →
ranking → filter → traverser → selector) over a frozen Query Contract
(Q1–Q5). Every result carries an explanation (reason/score).

**Why:** engineering users need to know *why* an item was returned. Ranking
weights come from configuration, never from the code, and are auditable.

## 8. The Librarian is the only write path

**Decision:** no component except the Librarian can create or mutate
knowledge; the write path is register → validate → canonicalize.

**Why:** a single write path makes validation, classification and lifecycle
rules enforceable by construction, not by convention.

## Non-goals (explicitly out of scope for v1.0)

- Semantic/embedding search (optional backend planned for v1.1, SSOT untouched).
- Event bus, graph engine as core features (documented as future extensions).
- Multi-writer concurrency within one process (AgentLock serializes writers).

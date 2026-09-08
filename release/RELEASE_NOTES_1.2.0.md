# HKOS v1.2.0 Release Notes — SQLite index backend + cross-project graph

**Date:** 2026-09-08
**Standard:** DS-017 v1.2 (IP-017-v1.2, ЭТАПЫ 1–4)
**Backward compatibility:** API unchanged; JSON backend remains the default;
SSOT (repository) is untouched by any backend change.

## Headline

1. **SQLite index backend** — write amplification is gone. Index updates
   become per-entity delta transactions (O(entity size) instead of rewriting
   all five `*.idx`); queries execute as SQL behind the same frozen
   IndexSnapshot contract. Choose it per deployment with
   `hkos.index.backend: sqlite` and migrate explicitly with `hkos migrate`.
   Measured ~73× faster index updates over 2000 sequential writes on an
   equal stand.
2. **Cross-project graph traversal** — `RelationshipTraverser` is now
   project-aware: a decision in project B that cites a fact in project A is
   returned by retrieval in B, deterministically, via Q4 and project
   snapshots — no vector search, no LLM.

## What changed

- `index/sqlite_store.py` — `SqliteIndexStore` (full IndexStore contract on
  stdlib sqlite3, WAL, per-project `indexes/index_store.db`), delta
  `update_entity`/`remove_entity`, `SqliteIndexSnapshot` (Q1–Q5 as SQL).
- `index/` typing — structural protocols `IndexStoreLike`/`SqliteStoreLike`
  (both backends accepted by IndexEngine/Builder/Validator/Manager).
- `index/relationship_index.py` — records carry `target_project_id`
  (additive; old data reads as `""`).
- `retrieval/relationship_traverser.py`, `retriever.py`,
  `retrieval_engine.py` — cross-project traversal via `snapshot_provider`.
- `services/librarian/librarian.py` — relation authoring normalizes a
  missing `source_id` to the owning entity (edges were previously dead for
  traversal) and generates a missing `relation_id`.
- `cli/` — new `hkos migrate` command; `hkos.status`/`doctor`/`validate`
  unchanged.
- Config: `hkos.index.backend` (json|sqlite) in development/production
  profiles; honored by MCP context and CLI.

## Migration

```
hkos migrate --check          # dry run
hkos migrate                  # convert all projects' JSON indexes
# config: hkos.index.backend: sqlite   # new writes take the delta path
```

SSOT is never touched by the migration; JSON `*.idx` stay in place, so
switching back is just reverting the config (and `hkos migrate --force`
re-imports from JSON if needed).

## Verification

- 987 tests pass (unit + integration, `-m "not sla"`); mypy strict 0;
  ruff F 0.
- Parity gates: sqlite.read == json.read for all five index docs on a real
  corpus (tags, negative kind, merge relations, empty tag/word lists);
  Q1–Q5 equality; stepwise add/update/delete delta parity; `hkos migrate`
  end-to-end (check → migrate → skip → force).
- E2E: retrieval on the SQLite hot path; cross-project retrieval (project B
  returns a related fact from project A); config-driven backend selection.

## Known notes

- Q4 relation ordering under *equal* `created_at` is a build-history
  artifact in JSON (not contractual); SQLite orders by rowid — parity
  tests compare canonically by (created_at, relation_id).
- Semantic search and FTS5 remain on the roadmap (optional backend, SSOT
  untouched).

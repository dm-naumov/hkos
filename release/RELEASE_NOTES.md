# HKOS v1.0.0 — Release Notes

**Date:** 2026-08-19

## What this is

HKOS (Hermes Knowledge OS) — a deterministic, object-oriented, file-based
engineering knowledge base for LLM agents: engineering memory, decisions,
negative knowledge, schema migrations, and performance instrumentation — all
independent of any LLM.

## Key features

- **Repository (SSOT)** + derived Index/Snapshot/Manifest/Cache — always
  rebuildable, never authoritative.
- **Full pipeline:** Project → Campaign → Task → Retrieval → Context → Save.
- **Negative knowledge** (FAILURE/DECISION/CONFIGURATION) — persisted and
  returned first when the same mistake is about to be repeated.
- **Migration Engine:** schema v1→v2→v3 + rollback (memory preserved),
  append-only event log, migration lock.
- **Hermes Integration:** migration.* commands, security
  (permissions/audit/AgentLock), multi-agent support.
- **Performance Layer:** SLA (retrieval <100 ms/10K, warm ~0.03 ms via
  IndexCache, cache hit >80%).
- **Production configuration profile;** documentation (8 guides).

## Known scale characteristics

- Cold retrieval parse O(index): 100K ≈ 1.1 s; the operational path is warm
  retrieval through IndexCache (≈0.03 ms).
- Full 1M stress and the 10000-cycle long-running run are dedicated windows
  (env-gated: HKOS_STRESS_SCALE / HKOS_LONG_CYCLES).
- File-based JSON storage: a backend plan is documented for 1M+.

## Quality

- 990+ tests (807 unit / 112 integration / 51+ system), all green.
- mypy --strict: 0 errors (272 files) · ruff: 0 functional findings ·
  compileall: clean.
- Crash-safe: kill -9 mid-write leaves zero partial records.

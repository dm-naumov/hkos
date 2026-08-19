# HKOS Roadmap

Current release: **v1.0.0** (2026-08) — core memory system, fully qualified
(15 sprints, 990+ tests, system-level acceptance).

## v1.1 — Adoption layer

- **MCP adapter** — a stdio MCP server exposing `retrieve / context / save /
  snapshot / doctor / status` so HKOS plugs into any MCP-capable client
  (Claude Desktop, IDEs, agent frameworks). Thin adapter over existing public
  APIs; zero business logic, zero daemons.
- **CLI package** — `hkos` command-line entry points (doctor is already a
  script; promote to a proper console-script package).
- **Semantic search as an optional backend** — pluggable embedding-based
  retrieval for fuzzy recall, layered on top of the existing Query Contract.
  SSOT, indexing and snapshot invariants remain untouched; deterministic
  retrieval stays the default.

## v1.2 — Scale & integration

- **SQLite storage backend** — same public API and envelope format, different
  storage engine behind `StorageEngine`; eases 1M+ corpora on single files.
- **Cross-project knowledge graphs** — relation queries across projects
  (existing relation model extended additively).
- **Backup strategies** — incremental snapshots, retention policies.

## Longer term (ideas, not commitments)

- Event hooks for agent frameworks (subscribe to knowledge lifecycle).
- Multi-writer concurrency (the AgentLock model already serializes writers;
  a file-watcher mode is the natural next step).
- Prebuilt agent-prompt packs for common engineering workflows.

## Principles that will not change

- Repository is the SSOT; derived artifacts stay rebuildable.
- The Librarian remains the only write path.
- Deterministic core: no LLM inside the memory pipeline.
- Additive evolution: no breaking API changes within 1.x.

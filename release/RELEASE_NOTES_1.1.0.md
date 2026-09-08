# HKOS v1.1.0 — Release Notes

**Date:** 2026-09-08

**Scope:** DS-017 v1.1 — graph authoring, save transparency, CLI package,
ecosystem presets, Failure Priority ranking. Roadmap v1.1 items.

## Highlights

- **Typed knowledge graph is now usable by agents.** `save` accepts
  `relations[]` (`target_id`, `relation_type`, optional `target_project_id`);
  the Librarian validates every edge deterministically (target exists —
  including cross-project lookups — no self-loops) and reports rejected links
  in `warnings` instead of failing silently. New relation semantics
  `BASED_ON` / `CAUSED_BY` / `MITIGATED_BY` trace ФАКТ → РЕШЕНИЕ → СБОЙ.
  `doctor` gained a `relations FK: dangling links` check.
- **Save is transparent.** When the deterministic classifier overrides an
  agent's category hint (or the hint is invalid), `save` answers with the
  rule id that fired (`rule:kind:negative`, `rule:marker:<CATEGORY>`,
  `rule:default:fact`) via `Librarian.explain_category()` /
  `KnowledgeClassifier.classify_with_rule()`.
- **`hkos` CLI** (doctor/status/validate) — terminal audits without a server;
  `scripts/doctor_cli.py` kept as a thin wrapper. Snapshot file persistence
  consolidated to `hkos.snapshot.file_persistence`.
- **Ecosystem presets**: Cursor/Windsurf MCP configs, LangChain/AutoGen wiring
  examples, and a runnable zero-LLM demo `examples/demo_failure_recovery.py`
  («Git for agent memory»: agent without HKOS repeats a failure; agent with
  HKOS retrieves the FAILURE record first and takes the right path).
- **Failure Priority is now real.** `failure` ranking factor — negative
  knowledge ranks above otherwise-equivalent candidates, labelled
  «Failure Priority» in explanations (previously claimed but not implemented).
  This is the property the demo asserts end-to-end.

## Compatibility

- 1.x additive only: no breaking API changes. KnowledgeRelation gained one
  optional field; RelationType gained three enum members; Librarian public API
  extended (`validate_relations`, `explain_category`); MCP `save` response
  carries `warnings`; retrieval gained a configurable ranking factor.
- Query Contract Q1–Q5 unchanged. Repository (SSOT) format unchanged.

## Configuration

- New: `retrieval.ranking.failure_weight` (default 0.05; 0 disables).

## Quality

- Full unit + integration suite: **970 passed** (1 environment-sensitive
  wall-clock SLA test excluded by the `sla` marker — known flake on this
  machine, fails identically on the previous release).
- mypy strict: 0 findings; ruff F: 0.
- Demo executable and asserted (FAILURE first + Failure Priority reason).

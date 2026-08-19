# Contributing to HKOS

Thanks for considering a contribution. HKOS is a long-lived knowledge base
engine with strict quality gates — please read this before opening a PR.

## Development setup

```bash
git clone <repo> hkos && cd hkos
uv venv .venv && source .venv/bin/activate
uv pip install -e ".[dev]"
```

## Quality gates (mandatory before every PR)

```bash
python -m compileall -f -q api campaign config context core docs index \
    integration kernel knowledge librarian migration performance project \
    repository retrieval scripts services snapshot storage tests utils __init__.py
.venv/bin/ruff check --select F .   # zero functional findings
.venv/bin/mypy .                    # strict, zero errors
.venv/bin/python -m pytest tests/unit tests/integration tests/architecture -q
```

Perf tests with wall-clock SLA thresholds are environment-sensitive (they can
flake under full-suite load but pass in isolation). If one fails, re-run it
alone before concluding there is a regression.

## Architecture rules (non-negotiable)

- **Repository is the SSOT.** Indexes, snapshots, manifests and caches are
  derived projections — never authoritative, always rebuildable.
- **The Librarian is the only write path** for knowledge.
- **Dependencies flow strictly downward** (core → storage → repository →
  index → retrieval/context/snapshot; services on top; migration is a
  maintenance layer; performance measures but never mutates).
- **No LLM in business logic.** Classification and retrieval are
  deterministic; ranking coefficients live in configuration, not in code.
- **No architecture change without a design note.** If your change touches
  layers, invariants, or the public API, describe the decision, alternatives
  and consequences in the PR description (docs/design/ for larger changes).

## Conventions

- Python 3.12+, type hints everywhere, frozen dataclasses for value types,
  constructor DI, no global singletons.
- Public API goes on the layer facade (IndexEngine / RetrievalEngine /
  SnapshotEngine / ...).
- Docstrings: summary + description (D-style is conventional).
- Value-type contracts are dataclasses; errors derive from HKOSError.

## Tests

- Unit + integration for every layer; system scenarios when the pipeline is
  touched (tests/system).
- System tests exercise public APIs only — no direct repository mutation,
  no writing to the index, snapshots are never treated as truth.
- Heavy scales are env-gated: `HKOS_STRESS_SCALE` (default 200K in-session,
  `1000000` for the full window) and `HKOS_LONG_CYCLES` (default 3000,
  `10000` full). These never run in CI.

## PR workflow

1. Branch from `main`: `git checkout -b feature/xxx`.
2. Implement + tests + docs, run the quality gates above.
3. Open the PR; CI runs `verify` (must be green) and `system` (informational).
4. Describe the change honestly: what, why, how verified.

## Reporting issues

Use the issue templates. For security problems see SECURITY.md.

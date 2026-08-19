# HKOS Developer Guide

## Package layout

hkos/: core, storage, repository, index, retrieval, context, snapshot, services,
kernel, migration, integration, performance. Tests: tests/unit, tests/integration,
tests/system (DS-014), tests/system/ds015 (DS-015).

## Conventions

- Layers: dependencies strictly downward; services orchestrate; migration is a
  maintenance layer; performance touches core only; kernel is the shared bottom.
- SSOT: the repository; derived artifacts (Index/Snapshot/Manifest/Cache) are
  never sources of truth.
- Writing knowledge: ONLY through the Librarian.
- Value types: frozen dataclasses; contracts expressed as dataclasses.
- Errors: HKOSError hierarchy (component="...").
- Wiring: constructor DI; no global singletons.

## Quality gates (mandatory)

```bash
python -m compileall -q .
.venv/bin/ruff check hkos/ tests/   # non-D = 0 (D docstring style is conventional)
.venv/bin/mypy .                    # strict, 0 errors
.venv/bin/python -m pytest tests/ -q
```

## Adding a feature

1. Public API goes on the layer facade (IndexEngine/RetrievalEngine/SnapshotEngine/...).
2. No business logic in performance/.
3. Tests: unit + integration (+ a system scenario when the pipeline is touched).
4. Docstring convention: summary + description (D-style allowed).

## Extending the Query Contract

Q1–Q5 are frozen (HKOS-INDEX-CONTRACT-001). New queries are additive (like ids()).

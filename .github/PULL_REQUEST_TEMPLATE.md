## What does this PR do?

<!-- One paragraph. If it touches architecture, include the design note:
decision, alternatives, consequences. -->

## Verification

- [ ] `compileall` passes
- [ ] `ruff check --select F .` — 0 findings
- [ ] `mypy .` — strict, 0 errors
- [ ] `pytest tests/unit tests/integration tests/architecture` — green
- [ ] System tests (if pipeline touched) — green locally
- [ ] Perf-flaky tests re-run in isolation if they failed in the full run

## Checklist

- [ ] Public API changes go through layer facades (no new write paths)
- [ ] No LLM/business-logic changes in `performance/`
- [ ] Docs updated (docs/, README if user-facing)
- [ ] Changelog entry added (release/CHANGELOG.md) for user-visible changes

## Notes for reviewers

<!-- Known limitations, follow-ups, deliberate deviations. -->

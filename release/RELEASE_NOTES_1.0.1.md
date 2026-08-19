# HKOS v1.0.1 — Patch Release Notes

**Date:** 2026-08-19

## Fixed

- **`LatencyTracker.percentile()` crash on a single measurement** under
  Python 3.12 (the supported minimum): `statistics.quantiles` requires at
  least two data points; a one-sample history now returns the sample value
  (any percentile of a single point is that point). Python 3.14's stdlib
  masked this in development; the fix is verified on 3.12 and 3.14.

## CI

- Wall-clock SLA latency tests are now `@pytest.mark.sla` and run in a
  dedicated informational `Perf SLA` job; the PR gate (`verify`) is stable
  on GitHub-hosted runners. Latency budgets remain documented in
  `release/BENCHMARKS.md` and `docs/performance-guide.md`.

## Quality

- Full verify suite: 949 passed (unit + integration + architecture),
  mypy --strict 0, ruff 0 functional findings — on Python 3.12 and 3.14.

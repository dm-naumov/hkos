# HKOS Production Checklist (v1.0.0)

## Configuration

- [x] config/hkos-production.yaml — valid (ConfigLoader.validate PASS)
- [x] hkos.version = 1.0.0
- [x] Operational parameters (auto_snapshot/auto_index/retrieve_before_task/save_after_task)
- [x] Performance (cache enabled/ttl 3600/max 1000), logging INFO, backup enabled

## Tests

- [x] unit+integration: 919 collected (918 passed; 1 known perf flake)
- [x] system (DS-014): 51 passed + 1 skipped (1M env gate)
- [x] system/ds015 (DS-015): 60+ passed (incl. sign-off)
- [x] compileall 0 / mypy strict 0 / ruff non-D 0

## Operations

- [x] Startup/Shutdown/Recovery procedures PASS
- [x] Backup/Restore PASS (before == after)
- [x] Migration/Rollback PASS (memory intact)
- [x] Kill -9 safe (no partial records)
- [x] Hermes compatibility PASS

## Performance

- [x] Retrieval cold <100 ms (100/10K); warm <10 ms; cache >80%
- [x] Context <200 ms; Snapshot <50 ms; Save <150 ms
- [x] Token reduction >60% (AGGRESSIVE)
- [x] Index build linear (O(N²) fix)

## Security

- [x] WRITE/ADMIN permissions; Audit (RECEIVED/ALLOWED/DENIED)
- [x] SSOT repository; derived artifacts recoverable

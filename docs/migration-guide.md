# HKOS Migration Guide

## When a migration is needed

A document schema change (schema_version = the `version` field of the HKOS-08
envelope). A missing version means legacy v1; a future version ABORTs.

## Order (mandatory)

Repository (apply) → Index rebuild → Snapshot regenerate → Validation.

## Run

```python
from hkos.migration import MigrationEngine, MigrationRegistry, MigrationStep
registry = MigrationRegistry()
registry.register(MigrationStep("001_mig", 1, 2))
# compose engine (see system tests) -> api
api.migrate()          # backup -> apply -> rebuild -> regenerate -> validate -> COMPLETED
api.status()           # "COMPLETED; current=2; target=2"
```

## Rollback

```python
api.rollback()         # restore + rebuild + regenerate + validate (F-2)
```

Rollback restores the repository from backup; Index/Snapshot are DELETED and
regenerated. The FSM is single-use: after FAILED/COMPLETED a new attempt
starts a fresh run.

## Safety

- Lock file migration.lock (stale threshold 30 min).
- Backup: backup/<migration_id>_<seq>/ — a copy of the Repository ONLY
  (indexes/snapshots excluded).
- History: append-only event log (multiple entries per migration allowed).
- VersionManifest: derived version cache (not SSOT); invalidated on rollback.

## Idempotency

Re-running with no pending changes = 0 changes (COMPLETED up-to-date).

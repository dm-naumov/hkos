# HKOS Deployment

## Requirements

- Linux, Python 3.12+, uv/venv
- Disk: 100K knowledge ≈ 100-150 MB; 1M ≈ 1-1.5 GB

## Install

```bash
cd hkos && uv venv .venv && source .venv/bin/activate && uv pip install -e .
```

## Run (production)

```python
from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.storage import StorageEngine

cfg = ConfigLoader(profile="production").load()
engine = StorageEngine(root="./hkos", config=cfg, logger=HKOSLogger(),
                       version=VersionManager())
engine.initialize()
```

## Backup (mandatory set)

Repository (projects/), config, migration history. Indexes/snapshots are
regenerated.

## Recovery

1. Repository from backup -> 2. Index rebuild -> 3. Snapshot regenerate ->
4. MigrationValidator.validate -> 5. Retrieval check.

## Migrations

MigrationEngine.migrate() (backup before any change); rollback restores.

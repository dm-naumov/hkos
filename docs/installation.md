# HKOS Installation

## Requirements

- Python 3.12+ (developed on 3.14), uv (or pip inside a venv)
- Linux / macOS / WSL

## Install

```bash
git clone <repo> hkos && cd hkos
uv venv .venv && source .venv/bin/activate
uv pip install -e .
```

## Configuration

- Development profile: `config/hkos-development.yaml` (default)
- Production profile: `config/hkos-production.yaml` (`ConfigLoader(profile="production")`)

## First run

```python
from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.storage import StorageEngine

cfg = ConfigLoader().load()          # development
engine = StorageEngine(root="./hkos", config=cfg,
                       logger=HKOSLogger(), version=VersionManager())
engine.initialize()                  # creates the directory layout (idempotent)
```

## Verify the install

```bash
python -m pytest tests/ -q
```

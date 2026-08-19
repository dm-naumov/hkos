# HKOS — Hermes Knowledge OS

[![CI](https://github.com/dnaumov/hkos/actions/workflows/ci.yml/badge.svg)](https://github.com/dnaumov/hkos/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue.svg)]()
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-990%2B-brightgreen.svg)]()
[![mypy](https://img.shields.io/badge/mypy-strict-2ea44f.svg)]()
[![ruff](https://img.shields.io/badge/ruff-0%20functional%20findings-2ea44f.svg)]()

**A deterministic, file-based engineering knowledge base for LLM agents.**

HKOS is a long-lived, object-oriented knowledge database designed to store and
structure engineering memory **independently of any LLM**. Knowledge is written
through a single canonical path, indexed locally, retrieved with a bounded
query contract, and snapshotted — all in plain JSON files, with no daemon, no
external services, and no embeddings.

> **Deterministic by design.** The classification, indexing, retrieval and
> lifecycle logic contains zero LLM calls. Your memory survives model swaps,
> prompt changes and vendor lock-in — the knowledge base is the source of
> truth, not the model.

---

## Why HKOS exists

LLM agent memory solutions today are typically **LLM-dependent**: embeddings,
model-generated "memories", and vector stores that only mean something to the
model that produced them. That design has a hard ceiling:

- memory quality silently changes when you swap the model;
- vector recall is probabilistic — the same query can return different results;
- there is no auditable, human-readable source of truth;
- failure modes are opaque and hard to debug.

HKOS takes the opposite position: **memory is engineering data**. It is
written deliberately, validated, versioned, and stored as plain JSON under a
single source of truth (SSOT). Retrieval is deterministic, explainable, and
fast enough for interactive agent use. This is what a production engineering
organization needs — not a black box.

## Architecture

```
                        ┌───────────────────────────────────────────┐
                        │ integration/   Hermes Agent adapters       │
                        │ migration/     schema migration FSM,       │
                        │                backup / rollback           │
                        └──────────────────────┬────────────────────┘
                                               ▼
                        ┌───────────────────────────────────────────┐
                        │ services/  Project · Campaign (FSM) ·      │
                        │            Librarian · MemoryService       │
                        └──────────────────────┬────────────────────┘
              ┌────────────────────────────────┼────────────────────────────────┐
              ▼                                ▼                                ▼
       retrieval/                       context/                        snapshot/
       deterministic ranking           context builder                 derived state,
       with explanations               (profiles, budgets)            versioned & diffed
              └────────────────────────────────┼────────────────────────────────┘
                                               ▼
                        ┌───────────────────────────────────────────┐
                        │ index/    5 indexes, Query Contract Q1–Q5, │
                        │           IndexCache (warm ≈ O(1))         │
                        └──────────────────────┬────────────────────┘
                                               ▼
                        ┌───────────────────────────────────────────┐
                        │ repository/  JSON Repository — the ONLY    │
                        │              source of truth (SSOT)        │
                        └──────────────────────┬────────────────────┘
                                               ▼
                        ┌───────────────────────────────────────────┐
                        │ storage/   StorageEngine, JSONStore,       │
                        │            HKOS-08 envelopes               │
                        └──────────────────────┬────────────────────┘
                                               ▼
                        ┌───────────────────────────────────────────┐
                        │ core/ · kernel/ · performance/             │
                        │ engine, config, logging · shared types ·   │
                        │ metrics & profiling (zero business logic)  │
                        └───────────────────────────────────────────┘
```

Dependencies flow strictly downward. `services/` orchestrates; `migration/` is
a maintenance layer on top; `performance/` measures but never mutates.

## Design invariants

1. **Repository is the single source of truth.** Indexes, snapshots,
   manifests and caches are *derived projections* — always rebuildable from
   the repository, never authoritative.
2. **The Librarian is the only write path for knowledge.** `register` →
   `validate` → `canonicalize` — no other component may create or mutate
   knowledge.
3. **Deterministic classification.** Categories (FACT, DECISION, FAILURE,
   CONFIGURATION, RULE, …) are assigned by a rule-based classifier — no LLM
   in the pipeline.
4. **Crash-safe writes.** All storage writes are atomic (tmp + rename).
   `kill -9` mid-write leaves either the old or the new record — never a
   partial one. Recovery is rebuild, not repair.
5. **Schema evolution is a first-class operation.** A migration FSM
   (backup → apply → rebuild index → regenerate snapshot → validate) with an
   append-only event log and idempotent rollback.
6. **No daemon, no global state, no hidden databases.** HKOS is a library;
   everything is files and injected dependencies (constructor DI).

## Knowledge lifecycle

```
register ──► NEW ──► VERIFIED ──► CANONICAL ──► ARCHIVED
                │        │
                └────────┴──► REJECTED / SUPERSEDED
```

- **NEW** — just registered, not yet part of retrievable memory;
- **VERIFIED** — passed validation;
- **CANONICAL** — the only status visible to retrieval (reusable);
- **ARCHIVED / REJECTED / SUPERSEDED** — filtered out of retrieval;
  negative knowledge (FAILURE with cause/fix) is kept and resurfaces first
  when the same mistake is about to be repeated.

## Quick start

```bash
pip install hkos          # Python 3.12+
# or, from a checkout:  uv venv .venv && uv pip install -e .
```

```python
# examples/quickstart.py — full pipeline on a throwaway corpus
from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.storage import StorageEngine
from hkos.repository.repository_manager import RepositoryManager
from hkos.repository.models import Knowledge
from hkos.services.project_manager import ProjectManager
from hkos.services.campaign_manager import CampaignManager
from hkos.services.librarian import Librarian
from hkos.index import IndexEngine, IndexStore, IndexCache, IndexQueryExecutor
from hkos.retrieval import RetrievalEngine

cfg = ConfigLoader().load()
engine = StorageEngine(root="./hkos", config=cfg,
                       logger=HKOSLogger(), version=VersionManager())
engine.initialize()
repos = RepositoryManager(engine)

project = ProjectManager(repos, HKOSLogger()).create(
    name="Demo", description="quickstart", tags=["demo"])
Librarian(repos, HKOSLogger()).register(project.id, Knowledge(
    title="TCP redirect works via nftables",
    body="meta l4proto tcp redirect to :12345", tags=["tcp", "nftables"]))

index = IndexEngine(repos, IndexStore(engine), HKOSLogger(), cache=IndexCache())
index.build(project.id)
retrieval = RetrievalEngine(repos, IndexQueryExecutor(IndexStore(engine), cache=IndexCache()),
                            cfg, HKOSLogger())
print(retrieval.retrieve("tcp redirect", project_id=project.id))
```

Real output of `python examples/quickstart.py`:

```
data root: /tmp/hkos-demo-x9wwf6se
project: 8c1bbd63-96ca-4c72-bd34-b70cae72bcc4
campaign: 9f00ff23-87d6-4ae5-a501-91406d50e72b
knowledge registered & canonicalized: 3
retrieval: 1 item(s) for 'udp proxy'
  [FAILURE] UDP traffic bypasses the proxy
snapshot: snapshot-00001 knowledge=3
OK
```

Note how the **negative knowledge** (the FAILURE entry) is what the retriever
returns for a query about a problem — that is HKOS's core value: past mistakes
are reused before they are repeated.

## Performance

Measured on a stock Linux workstation, corpus generated deterministically
(no LLM involvement). Full methodology and reproduction scripts in
[`release/BENCHMARKS.md`](release/BENCHMARKS.md).

| Operation | Budget (SLA) | Measured |
|---|---|---|
| Retrieval, cold (10K knowledge) | < 100 ms | PASS |
| Retrieval, warm (IndexCache) | — | ~0.03 ms (2120× faster than cold) |
| Context build (10K) | < 200 ms | PASS |
| Save (register → canonicalize) | < 150 ms | PASS |
| Snapshot load / create / diff | < 50 / < 300 / < 500 ms | PASS |
| Migration detect @100K | < 100 ms | < 25 ms (VersionManifest; was 1470 ms) |
| Migration backup / rollback / validate | < 5 / < 10 / < 10 s | 2.8 / 3.2 / 7.2 s |
| Index build 30K | linear | 1.5 s (was 84.6 s — O(N²) removed) |
| 100K knowledge, full corpus | — | generate 19.4 s · RAM 85 MB · retrieval < 100 ms |
| 1M stress | — | mechanism validated (200K in-session); full run via `HKOS_STRESS_SCALE=1000000` |
| Crash safety | — | `kill -9` mid-write: zero partial records (atomic tmp+rename) |

## Quality

- **990+ tests** — 807 unit, 112 integration, 51+ system-level scenarios
  (pipeline, lifecycle, 10K growth, consistency, failure recovery, concurrent
  agents, migration, security, 100K stress, long-running, operational).
- **mypy --strict: 0 errors** across 272 files.
- **ruff: 0 functional findings** (docstring style only).
- **compileall: clean.**
- All layers tested at unit + integration level; system tests exercise only
  public APIs (SSOT discipline is itself enforced by tests).

## How is this different?

| | HKOS | Mem0 / basic-memory | Vector-store agent memory |
|---|---|---|---|
| Memory source of truth | JSON repository (files) | internal store, LLM-extracted | embeddings (model-dependent) |
| Determinism | yes — same query, same result | no — model-dependent | no — approximate |
| LLM needed to *read* memory | no | no | yes (embedding model) |
| LLM needed to *write* memory | no (rule-based classifier) | yes (extraction prompt) | yes |
| Auditable / diffable | yes (plain JSON, snapshots, diff) | limited | no |
| Schema migration | first-class FSM + rollback | — | — |
| Crash-safe | atomic writes, `kill -9`-proof | — | — |
| Explains why an item was retrieved | yes (reason/score per item) | no | no |

**In one sentence:** most agent-memory tools make memory *another model's
output*; HKOS makes memory *your engineering data* — deterministic, versioned,
auditable, and portable across LLMs.

## Documentation

- [Installation](docs/installation.md)
- [Architecture](docs/architecture.md)
- [API reference](docs/api-reference.md)
- [Developer guide](docs/developer.md)
- [Performance guide](docs/performance-guide.md)
- [Migration guide](docs/migration-guide.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Administrator guide](docs/administrator.md)

## Roadmap

- **v1.0** — current: core, storage, repository, index, retrieval, context,
  snapshot, services, migration, integration, performance layers.
- **v1.1** — MCP adapter (stdio server for any MCP client), semantic search as
  an *optional* backend (SSOT untouched), CLI package.
- **v1.2** — SQLite storage backend (same API, envelope format preserved),
  cross-project knowledge graphs.

## License

MIT — see [LICENSE](LICENSE).

---

*HKOS was developed in 15 certified sprints (DS-001…DS-015) with a documented
engineering process: architecture reviews, adversarial audits, performance
budgets, and system-level qualification. Design decisions are documented in
[`docs/design/`](docs/design/).*

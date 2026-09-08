# HKOS API Reference

## Core

- ConfigLoader(profile) → load()/validate()/get(key)/reload()
- HKOSLogger, VersionManager, HKOSError (component)

## Storage

- StorageEngine(root, config, logger, version) → initialize()/storage()

## Repository (SSOT)

- RepositoryManager → projects/campaigns/knowledge/decisions/artifacts
- BaseRepository: save/load/update/delete/exists/list/count

## Index

- IndexEngine: build/rebuild/update/remove/validate/statistics/optimize/health
- IndexQueryExecutor (Q1–Q5): keyword_search/tag_search/entity_get/relations/statistics; snapshot()
- IndexCache: get/set/invalidate/clear

## Retrieval

- RetrievalEngine.retrieve(query, project_id, campaign_id, top_n, include_history) → RetrievalResult
- RetrievalItem: entity/entity_type/explanation (reason/score/...)

## Context

- ContextBuilder.build(result, project_id) → ContextDocument (items/sections/estimates)

## Snapshot

- SnapshotEngine: create(project, reason, force)/load(project, version)/history/validate

## Services

- ProjectManager: create/info/list/update/close/archive/...
- CampaignManager: create/open/pause/resume/close/status (FSM CREATED→…→COMPLETED)
- Librarian: register/update/canonicalize/merge/archive/restore/reject/
  detect_conflicts/recalculate_confidence/history/validate/
  validate_relations/explain_category
- KnowledgeClassifier: classify(knowledge); classify_with_rule(knowledge) →
  (category, rule_id). Детерминированная классификация (DS-017 §4.3.1):
  kind='negative' → FAILURE; маркеры title/body → категория; иначе FACT.
  register игнорирует предзаполненный knowledge.category (hint) — финальная
  категория всегда от классификатора, если не передан явный параметр
  category; explain_category возвращает решение с id правила для
  прозрачности (warnings в MCP save).
- MemoryService: resolve_project/resolve_campaign/prepare_context/save_results/drain_pending

## Migration (DS-011)

- MigrationEngine: detect/migrate/rollback/validate/backup/history/status (+acquire_lock/release_lock)
- MigrationRegistry: register/ordered/contains; SchemaDetector: detect(project_ids) → SchemaInfo
- VersionManifest: load/save/get/set/invalidate

## Integration (Hermes, DS-012)

- MigrationTools (6 operations), MigrationCommandRegistry (migration.*), schemas (typed responses),
  security (AgentContext/check_permission/MigrationSafetyGuard), AuditLogger, FallbackPolicy,
  AgentLock (READ/WRITE/MIGRATION)

## Performance (DS-013)

- PerformanceManager: start/stop/statistics/profile/health/reset/optimize/measure
- MetricsEngine/LatencyTracker/Profiler/ResourceMonitor/CacheManager/PerformanceContextOptimizer
- PerformanceIntegration: wrap_retrieval/context/snapshot/save/index; create_performance_layer

## SnapshotPersistence port

latest(project)/version(project, v)/save(project, doc)/history(project)/append_history

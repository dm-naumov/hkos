# HKOS Configuration

Profiles: development (config/hkos-development.yaml), production
(config/hkos-production.yaml).

## Key sections

- hkos: version, root, enabled
- core.bootstrap: auto_start, health_check_on_start
- logging: level (INFO in production), max_size_mb, backup_count
- health: check_interval_seconds, components
- retrieval: ranking (DS-008 weights), parser (topics/entities/stopwords/intents),
  selector/builder/traverser
- operations: auto_snapshot, auto_index, retrieve_before_task, save_after_task,
  context_profile
- performance: cache (enabled/max_entries/ttl_seconds), context.compression, metrics
- backup: enabled, keep_n

Loading: ConfigLoader(profile=...).load() -> validate().

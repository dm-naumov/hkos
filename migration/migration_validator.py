"""HKOS Migration Validator (DS-011 Rev.1.2 §13, IP-011 ЭТАП 4)
==============================================================
Оркестрационный валидатор после миграции. ТОЛЬКО проверяет:
- НЕ изменяет данные; НЕ пишет; НЕ создаёт backup; НЕ выполняет
  rollback; НЕ выполняет rebuild;
- работает ТОЛЬКО через существующие публичные интерфейсы:
  RepositoryManager (структура/ссылки/счётчики), IndexEngine
  (validate/statistics — существующий IndexValidator), SnapshotEngine
  (load/validate — существующий SnapshotValidator), classification_policy
  (корректность классификации), порт version_reader (конверты).

Проверки (DS-011 §13):
1. структура документов (парсинг через публичное чтение; выборка N);
2. валидность envelope.version (1 <= v <= target; порт чтения конвертов);
3. ссылочная целостность (parent_ids/canonical_id/source_campaign;
   выборка N, детерминированная — первые N по отсортированному id);
4. валидность индекса (IndexEngine.validate — существующий IndexValidator);
5. семантическая проверка Snapshot:
   - совпадение счётчиков (snapshot.statistics vs Repository);
   - отсутствие orphan-ссылок (SnapshotEngine.validate — существующий
     SnapshotValidator);
   - корректность секций (элемент секции имеет id);
   - совпадение snapshot/index (статистика снимка vs индекс, Q5);
   - корректность classification (policy.classify -> ожидаемая секция).

Любая ошибка -> raise MigrationValidationError.
"""

from typing import Callable

from hkos.index.index_engine import IndexEngine
from hkos.index.validation import ValidationResult
from hkos.migration.exceptions import MigrationValidationError
from hkos.repository.repository_manager import RepositoryManager
from hkos.services.classification_policy import (
    CATEGORY_ARCHITECTURE,
    CATEGORY_ARTIFACT,
    CATEGORY_CANONICAL,
    CATEGORY_CONFIGURATION,
    CATEGORY_DECISION,
    CATEGORY_FAILURE,
    CATEGORY_LIMITATION,
    CATEGORY_QUESTION,
    classify,
)
from hkos.snapshot.snapshot_engine import SnapshotEngine

__all__ = ["MigrationValidator"]

# Секции Snapshot (DS-010 §8) по логической категории classification_policy.
_SECTION_BY_CATEGORY: dict[str, str] = {
    CATEGORY_CANONICAL: "Canonical Knowledge",
    CATEGORY_ARCHITECTURE: "Architecture",
    CATEGORY_DECISION: "Accepted Decisions",
    CATEGORY_CONFIGURATION: "Configurations",
    CATEGORY_FAILURE: "Known Failures",
    CATEGORY_LIMITATION: "Known Limitations",
    CATEGORY_ARTIFACT: "Artifacts",
    CATEGORY_QUESTION: "Open Questions",
}


class MigrationValidator:
    """Валидатор целостности после миграции (DS-011 §13)."""

    def __init__(
        self,
        repository: RepositoryManager,
        index_engine: IndexEngine,
        snapshot_engine: SnapshotEngine,
        version_reader: Callable[[str], list[int]],
        sample_size: int = 1000,
    ) -> None:
        """Инициализация валидатора.

        Args:
            repository: RepositoryManager (публичный интерфейс чтения).
            index_engine: IndexEngine (validate/statistics).
            snapshot_engine: SnapshotEngine (load/validate).
            version_reader: Порт чтения envelope.version документов
                (вне слоя; отсутствующий version -> 1, legacy).
            sample_size: Размер детерминированной выборки (N).

        """
        self._repository = repository
        self._index_engine = index_engine
        self._snapshot_engine = snapshot_engine
        self._version_reader = version_reader
        self._sample_size = sample_size

    def validate(self, target_version: int) -> ValidationResult:
        """Валидация после миграции (все проекты рабочей области).

        Args:
            target_version: Ожидаемая версия схемы после миграции.

        Returns:
            ValidationResult (валидный случай).

        Raises:
            MigrationValidationError: любая ошибка проверки (DS-011 §13).

        """
        errors: list[str] = []
        warnings: list[str] = []
        projects = self._repository.projects.list()
        for project_entity in projects:
            project = project_entity.id
            self._check_versions(project, target_version, errors)
            self._check_documents(project, errors)
            self._check_index(project, errors)
            self._check_snapshot(project, errors)
        result = ValidationResult(valid=not errors, errors=errors, warnings=warnings)
        if not result.valid:
            raise MigrationValidationError(
                "Migration validation failed: " + "; ".join(result.errors)
            )
        return result

    def _check_versions(
        self, project: str, target_version: int, errors: list[str]
    ) -> None:
        """Валидность envelope.version: 1 <= v <= target (конверты)."""
        try:
            versions = self._version_reader(project)
        except Exception as exc:  # порт недоступен -> ошибка структуры
            errors.append(f"{project}: envelope read failed: {exc}")
            return
        invalid = sorted(v for v in versions if v < 1 or v > target_version)
        if invalid:
            errors.append(
                f"{project}: invalid envelope.version(s) {invalid} "
                f"(expected 1..{target_version})"
            )

    def _check_documents(self, project: str, errors: list[str]) -> None:
        """Структура документов (парсинг) + ссылочная целостность (выборка)."""
        try:
            entities = self._repository.knowledge.list(project)
        except Exception as exc:
            errors.append(f"{project}: document structure broken: {exc}")
            return
        sampled = sorted(entities, key=lambda e: e.id)[: self._sample_size]
        for entity in sampled:
            refs: list[str] = []
            for parent in getattr(entity, "parent_ids", []) or []:
                refs.append(str(parent))
            canonical_id = getattr(entity, "canonical_id", "") or ""
            if canonical_id:
                refs.append(str(canonical_id))
            for ref in refs:
                try:
                    exists = self._repository.knowledge.exists(project, ref)
                except Exception as exc:
                    errors.append(f"{project}: ref check failed {ref}: {exc}")
                    continue
                if not exists:
                    errors.append(f"{project}: broken reference {ref} (knowledge)")
            campaign = getattr(entity, "source_campaign", "") or ""
            if campaign:
                try:
                    exists = self._repository.campaigns.exists(project, campaign)
                except Exception as exc:
                    errors.append(f"{project}: campaign ref check failed: {exc}")
                    continue
                if not exists:
                    errors.append(
                        f"{project}: broken campaign reference {campaign}"
                    )

    def _check_index(self, project: str, errors: list[str]) -> None:
        """Валидность индекса через существующий IndexValidator."""
        try:
            result = self._index_engine.validate(project)
        except Exception as exc:
            errors.append(f"{project}: index validation failed: {exc}")
            return
        if not result.valid:
            errors.extend(f"{project}: index: {e}" for e in result.errors)

    def _check_snapshot(self, project: str, errors: list[str]) -> None:
        """Семантическая проверка Snapshot (после миграции снимок обязан
        существовать — пересоздан).
        """
        try:
            snapshot = self._snapshot_engine.load(project)
        except Exception as exc:
            errors.append(f"{project}: snapshot load failed: {exc}")
            return
        if snapshot is None:
            errors.append(
                f"{project}: snapshot missing (must be regenerated after migration)"
            )
            return
        # структурная проверка (ссылки/orphan/UUID) — существующий SnapshotValidator
        try:
            structural = self._snapshot_engine.validate(snapshot)
        except Exception as exc:
            errors.append(f"{project}: snapshot validation failed: {exc}")
            return
        if not structural.valid:
            errors.extend(f"{project}: snapshot: {e}" for e in structural.errors)
        # совпадение счётчиков: snapshot.statistics vs Repository
        expected = {
            "knowledge": self._repository.knowledge.count(project),
            "decisions": self._repository.decisions.count(project),
            "campaigns": self._repository.campaigns.count(project),
            "artifacts": self._repository.artifacts.count(project),
        }
        for key, expected_count in expected.items():
            actual = snapshot.statistics.get(key)
            if actual is not None and int(actual) != expected_count:
                errors.append(
                    f"{project}: snapshot counter {key} = {actual}, "
                    f"repository = {expected_count}"
                )
        # совпадение snapshot/index (пересечение ключей статистики)
        try:
            index_stats = self._index_engine.statistics(project)
        except Exception:
            index_stats = {}
        for key, actual in snapshot.statistics.items():
            index_value = index_stats.get(key)
            if index_value is not None and int(index_value) != int(actual):
                errors.append(
                    f"{project}: snapshot/index mismatch {key}: "
                    f"snapshot={actual} index={index_value}"
                )
        # корректность секций и классификации (детерминированная выборка)
        for section_name, entries in (snapshot.sections or {}).items():
            if not isinstance(entries, list):
                # Секции-метаданные (например, "Project Metadata" — объект,
                # а не список записей) не участвуют в проверке записей.
                continue
            for entry in sorted(
                (e for e in entries if isinstance(e, dict)),
                key=lambda e: str(e.get("id", "")),
            )[: self._sample_size]:
                entity_id = entry.get("id", "")
                if not entity_id:
                    errors.append(
                        f"{project}: section {section_name!r}: entry without id"
                    )
                    continue
                self._check_classification(
                    project, section_name, str(entity_id), errors
                )

    def _check_classification(
        self, project: str, section_name: str, entity_id: str, errors: list[str]
    ) -> None:
        """Корректность классификации: policy.classify -> ожидаемая секция."""
        loaded = self._load_entity(project, entity_id)
        if loaded is None:
            errors.append(
                f"{project}: snapshot entry {entity_id} missing in repository"
            )
            return
        entity_type, entity = loaded
        if entity_type in ("project", "campaign"):
            # Проект и кампания — метаданные, не классифицируемые сущности;
            # их записи в секциях (по построению SnapshotBuilder — Open
            # Questions) не проверяются на классификацию.
            return
        logical = classify(
            entity_type=entity_type,
            category=getattr(entity, "category", "") or "",
            kind=getattr(entity, "kind", "") or "",
            status=getattr(entity, "status", "") or "",
        )
        expected_section = _SECTION_BY_CATEGORY.get(logical)
        if expected_section is not None and expected_section != section_name:
            errors.append(
                f"{project}: classification mismatch: {entity_id} in "
                f"{section_name!r}, expected {expected_section!r} (logical {logical})"
            )

    def _load_entity(
        self, project: str, entity_id: str
    ) -> tuple[str, object] | None:
        """Загрузка сущности (entity_type, entity) через публичные интерфейсы."""
        for entity_type, repo in (
            ("knowledge", self._repository.knowledge),
            ("decision", self._repository.decisions),
            ("artifact", self._repository.artifacts),
            ("campaign", self._repository.campaigns),
            ("project", self._repository.projects),
        ):
            try:
                if repo.exists(project, entity_id):
                    return entity_type, repo.load(project, entity_id)
            except Exception:
                continue
        return None

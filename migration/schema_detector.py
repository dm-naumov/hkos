"""HKOS Schema Detector (DS-011 Rev.1.2 §11, DS-013 ЭТАП 2)
============================================================
Определение текущей версии схемы. Детерминированный.

Источники:
- Repository — единственный источник истины (envelope.version);
- VersionManifest — ПРОИЗВОДНЫЙ КЭШ: при валидном и ПОЛНОМ manifest'е
  detect читает ТОЛЬКО manifest (без сканирования документов);
  при отсутствии/повреждении/неполноте — полный fallback-скан через
  порт version_reader (старое поведение 100%), с параллельным чтением
  по проектам (детерминированный результат, ошибки не скрываются).

Правила (DS-013 ЭТАП 2):
- manifest не источник истины; «Repository wins»;
- после успешного fallback-обнаружения manifest может быть обновлён;
- неизвестная будущая версия (> target) -> MigrationError (ABORT).
"""

import json  # noqa: F401  (сохранено для совместимости импортов)
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from hkos.migration.exceptions import MigrationError
from hkos.migration.migration_registry import MigrationRegistry
from hkos.migration.version_manifest import VersionManifest

__all__ = ["SchemaInfo", "SchemaDetector"]


@dataclass(frozen=True)
class SchemaInfo:
    """Результат определения версии схемы."""

    current_version: int
    target_version: int
    pending: list[str] = field(default_factory=list)
    mixed: bool = False


class SchemaDetector:
    """Детектор версии схемы (manifest-кэш + fallback-скан)."""

    _MAX_WORKERS = 8

    def __init__(
        self,
        registry: MigrationRegistry,
        version_reader: Callable[[str], list[int]],
        manifest: VersionManifest | None = None,
    ) -> None:
        """Инициализация детектора.

        Args:
            registry: Каталог миграций (целевая версия).
            version_reader: Порт чтения envelope.version документов
                (вне слоя; отсутствующий version -> 1, legacy).
            manifest: Производный кэш версий (опционально; DS-013).

        """
        self._registry = registry
        self._version_reader = version_reader
        self._manifest = manifest

    def detect(self, project_ids: list[str]) -> SchemaInfo:
        """Определить версию схемы: manifest (если полон/валиден),
        иначе fallback-скан конвертов (параллельно по проектам).

        Args:
            project_ids: UUID проектов рабочей области.

        Raises:
            MigrationError: неизвестная будущая версия (ABORT, §11).

        """
        versions = self._manifest_versions(project_ids)
        if versions is None:
            versions = self._scan_versions(project_ids)
        target = self._target_version()
        if not versions:
            return SchemaInfo(
                current_version=target, target_version=target)
        future = sorted(v for v in versions if v > target)
        if future:
            raise MigrationError(
                f"Unknown future schema version: {future} > target {target} (ABORT)"
            )
        current = min(versions)
        mixed = len(set(versions)) > 1
        pending = [
            step.migration_id
            for step in self._registry.ordered(current, target)
        ]
        return SchemaInfo(
            current_version=current,
            target_version=target,
            pending=pending,
            mixed=mixed,
        )

    # ---- manifest-путь (быстрый; кэш, не истина) ----

    def _manifest_versions(self, project_ids: list[str]) -> list[int] | None:
        """Версии из manifest; None — если manifest отсутствует,
        невалиден или неполон (тогда — fallback-скан).
        """
        manifest = self._manifest
        if manifest is None:
            return None
        if not manifest.is_valid():
            return None
        if not manifest.covers(project_ids):
            return None
        return manifest.schema_versions(project_ids)

    # ---- fallback-путь (полный скан; старое поведение) ----

    def _scan_versions(self, project_ids: list[str]) -> list[int]:
        """Полный скан конвертов (параллельно по проектам; результат
        детерминирован — порядок проектов сохраняется; ошибки не
        скрываются). После успешного скана manifest обновляется.
        """
        versions: list[int] = []
        if len(project_ids) <= 1:
            for project in project_ids:
                versions.extend(self._version_reader(project))
        else:
            with ThreadPoolExecutor(
                max_workers=min(self._MAX_WORKERS, len(project_ids))
            ) as pool:
                for project_versions in pool.map(self._version_reader, project_ids):
                    versions.extend(project_versions)
        manifest = self._manifest
        if manifest is not None:
            current = min(versions) if versions else self._target_version()
            for project in project_ids:
                manifest.set(project, current)
            manifest.save()
        return versions

    def _target_version(self) -> int:
        """Требуемая версия: последняя зарегистрированная (или 1)."""
        target = 1
        for step in self._registry.steps():
            target = max(target, step.to_version)
        return target

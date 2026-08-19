"""HKOS Version Manifest (DS-013 ЭТАП 2)
==========================================
ПРОИЗВОДНЫЙ КЭШ версий схемы (НЕ источник истины).

- Repository остаётся единственным SSOT; envelope.version — истина;
- manifest НЕ хранит знания/документы; НЕ заменяет Repository;
- при отсутствии/повреждении/неполноте manifest'а — fallback на полный
  скан (старое поведение 100%);
- «Repository wins»: при подозрении на рассинхронизацию manifest
  инвалидируется и пересоздаётся сканом.

Формат:
    {"projects": {project_id: {"schema_version": N, "updated_at": iso}}}
"""

import json
import time
from pathlib import Path
from typing import Final

__all__ = ["VersionManifest"]

_MANIFEST_KEY: Final[str] = "projects"
_VERSION_KEY: Final[str] = "schema_version"
_UPDATED_KEY: Final[str] = "updated_at"


class VersionManifest:
    """Производный кэш версий схемы проектов (файл JSON)."""

    def __init__(self, path: Path) -> None:
        """Инициализация.

        Args:
            path: Путь к файлу manifest (version_manifest.json).

        """
        self._path = Path(path)
        self._projects: dict[str, dict[str, object]] = {}
        self._valid = False

    # ---- чтение ----

    def load(self) -> None:
        """Загрузить manifest из файла. Битый/отсутствующий файл ->
        пустой и невалидный (без исключения; fallback на скан).
        """
        self._projects = {}
        self._valid = False
        try:
            raw = json.loads(self._path.read_text())
        except Exception:
            return
        projects = raw.get(_MANIFEST_KEY)
        if not isinstance(projects, dict):
            return
        cleaned: dict[str, dict[str, object]] = {}
        for project_id, entry in projects.items():
            if not isinstance(entry, dict):
                continue
            version = entry.get(_VERSION_KEY)
            if not isinstance(version, int) or version < 1:
                continue
            cleaned[str(project_id)] = {
                _VERSION_KEY: version,
                _UPDATED_KEY: str(entry.get(_UPDATED_KEY, "")),
            }
        if not cleaned:
            return
        self._projects = cleaned
        self._valid = True

    def is_valid(self) -> bool:
        """Манифест валиден (загружен и содержит данные)."""
        return self._valid

    def covers(self, project_ids: list[str]) -> bool:
        """Манифест ПОЛОН для запрошенных проектов (все присутствуют)."""
        return all(project_id in self._projects for project_id in project_ids)

    def schema_versions(self, project_ids: list[str]) -> list[int]:
        """Версии схемы для проектов (в порядке запроса)."""
        versions: list[int] = []
        for project_id in project_ids:
            entry = self._projects.get(project_id)
            if entry is None:
                continue
            version = entry.get(_VERSION_KEY)
            if isinstance(version, int):
                versions.append(version)
        return versions

    # ---- запись (только после успешного обнаружения/миграции) ----

    def set(self, project_id: str, version: int) -> None:
        """Обновить версию проекта в памяти (с отметкой времени)."""
        self._projects[str(project_id)] = {
            _VERSION_KEY: version,
            _UPDATED_KEY: time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        self._valid = True

    def save(self) -> None:
        """Атомарная запись manifest (tmp + rename)."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {_MANIFEST_KEY: self._projects}
        tmp = self._path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True))
        tmp.replace(self._path)

    def invalidate(self) -> None:
        """Инвалидация: manifest удаляется («Repository wins»; следующий
        detect выполнит fallback-скан и пересоздаст manifest).
        """
        self._projects = {}
        self._valid = False
        try:
            self._path.unlink()
        except OSError:
            pass

    def size(self) -> int:
        """Количество проектов в manifest."""
        return len(self._projects)

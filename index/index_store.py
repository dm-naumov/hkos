"""HKOS Index Store (DS-007 §11)
==============================
IndexStore — единственная точка персистентности файлов индексов.

Файлы индексов хранятся в projects/<p>/indexes/<name>.idx (HKOS-02 §16)
и являются JSON-документами с конвертом HKOS-08 (schema/version/...),
что допускает будущую миграцию на SQLite без изменения API (DS-007 §11).

IndexStore — ЕДИНСТВЕННЫЙ компонент Index Layer с доступом к Storage
(инжектируется на уровне композиции, как у Repository). Все остальные
модули index/ работают только через IndexStore и RepositoryManager.
"""
import os
from pathlib import Path

from hkos.storage.path_manager import PathManager
from hkos.storage.storage_engine import StorageEngine

__all__ = ["IndexStore"]

# Имена файлов индексов (DS-007 §11).
INDEX_KEYWORD: str = "keyword"
INDEX_TAGS: str = "tags"
INDEX_ENTITIES: str = "entities"
INDEX_RELATIONS: str = "relations"
INDEX_STATISTICS: str = "statistics"

INDEX_NAMES: tuple[str, ...] = (
    INDEX_KEYWORD,
    INDEX_TAGS,
    INDEX_ENTITIES,
    INDEX_RELATIONS,
    INDEX_STATISTICS,
)


class IndexStore:
    """Персистентность файлов индексов (документы с конвертом HKOS-08)."""

    def __init__(self, storage: StorageEngine) -> None:
        """Инициализация хранилища индексов.

        Args:
            storage: StorageEngine (инжектируется на уровне композиции).

        """
        self._storage = storage

    @property
    def storage(self) -> StorageEngine:
        """Используемый StorageEngine."""
        return self._storage

    def _path(self, project: str, index_name: str) -> str:
        """Путь файла индекса (только через PathManager)."""
        return PathManager.index_file(self._storage.root, project, index_name)

    def read(self, project: str, index_name: str) -> dict[str, object] | None:
        """Прочитать данные индекса (раздел data конверта); None, если нет.

        Файл хранит конверт HKOS-08 (schema/type/version/created_at/
        updated_at/data); наружу отдаётся только раздел data.
        """
        path = self._path(project, index_name)
        if not self._storage.exists(path):
            return None
        doc = self._storage.read_json(path)
        data = doc.get("data")
        if not isinstance(data, dict):
            return {}
        return data

    def write(self, project: str, index_name: str, doc: dict[str, object]) -> None:
        """Атомарно записать документ индекса."""
        path = self._path(project, index_name)
        self._storage.mkdir(os.path.dirname(path))
        self._storage.write_json(path, doc)

    def fingerprint(self, project: str) -> tuple[tuple[str, int, int], ...]:
        """Отпечаток файлов индекса проекта ((имя, mtime_ns, size)).

        Используется IndexCache для обнаружения внешних изменений без
        полного hash больших индексов на каждый запрос (DS-013 ЭТАП 3).
        Отсутствующий файл -> (имя, -1, -1).
        """
        names = ("keyword", "tags", "entities", "relations", "statistics")
        result: list[tuple[str, int, int]] = []
        for name in names:
            path = Path(self._path(project, name))
            try:
                stat = path.stat()
                result.append((name, stat.st_mtime_ns, stat.st_size))
            except OSError:
                result.append((name, -1, -1))
        return tuple(result)

    def exists(self, project: str, index_name: str) -> bool:
        """Проверить существование файла индекса."""
        return self._storage.exists(self._path(project, index_name))

    def delete(self, project: str, index_name: str) -> None:
        """Удалить файл индекса (используется при rebuild/перестройке)."""
        path = self._path(project, index_name)
        if self._storage.exists(path):
            self._storage.delete(path)

    def list_names(self, project: str) -> list[str]:
        """Имена файлов индексов, существующих для проекта."""
        index_dir = PathManager.indexes(self._storage.root, project)
        if not self._storage.exists(index_dir):
            return []
        return [
            name[: -len(".idx")]
            for name in self._storage.list(index_dir)
            if name.endswith(".idx")
        ]

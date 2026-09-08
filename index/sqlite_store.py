"""HKOS SQLite Index Store (DS-017 §4.1, IP-017-v1.2 ЭТАП 1a).

Персистентный бэкенд индексов на SQLite (stdlib sqlite3, zero deps):
per-project файл projects/<pid>/indexes/index_store.db, WAL.

Контракт — как у IndexStore (read/write/exists/delete/list_names/fingerprint),
но данные зеркалируются в таблицы. Восстановление из строк сохраняет
структуру и ПОРЯДОК списков JSON-формата (rowid/seq = порядок вставки) —
parity с JSON-бэкендом гарантируется тестами.

Схема (v1):
  kw(id...)/kw_ew        keyword: postings {word: [entries]}, entity_words
  tg/tg_et               tags:     tags {tag: [entries]}, entity_tags
  en                     entities: entities {id: record}
  rel                    relations: entity_relations/out/in (rowid-порядок)
  st                     statistics: {key: count}
  meta                   признак существования индекс-дока (0-строковые доки)
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from hkos.storage.path_manager import PathManager
from hkos.storage.storage_engine import StorageEngine

__all__ = ["SqliteIndexStore", "INDEX_STORE_DB"]

INDEX_STORE_DB: str = "index_store.db"

# Имена индекс-доков (совпадают с IndexStore.INDEX_NAMES).
_INDEX_NAMES: tuple[str, ...] = (
    "keyword", "tags", "entities", "relations", "statistics",
)

# Типы сущностей для statistics — только в codecs (data приходит из JSON-дока).


class SqliteIndexStore:
    """Персистентность индексов проекта в SQLite (per-project, WAL)."""

    def __init__(self, storage: StorageEngine) -> None:
        """Инициализация (storage — корень HKOS, как у IndexStore)."""
        self._storage = storage

    # --- Соединение / схема ---

    def _db_path(self, project: str) -> Path:
        """Путь БД проекта: projects/<pid>/indexes/index_store.db."""
        index_dir = PathManager.indexes(self._storage.root, project)
        return Path(index_dir) / INDEX_STORE_DB

    def _connect(self, project: str) -> sqlite3.Connection:
        """Открыть соединение (создаёт каталог и схему при необходимости)."""
        db_path = self._db_path(project)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(str(db_path))
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=NORMAL")
        self._init_schema(con)
        return con

    @staticmethod
    def _init_schema(con: sqlite3.Connection) -> None:
        """Создать таблицы схемы v1 (идемпотентно)."""
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS meta(
                name TEXT PRIMARY KEY, present INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS kw(
                word TEXT NOT NULL, id TEXT NOT NULL, type TEXT NOT NULL,
                project TEXT NOT NULL,
                PRIMARY KEY(word, id));
            CREATE TABLE IF NOT EXISTS kw_ew(
                entity_id TEXT NOT NULL, word TEXT NOT NULL, seq INTEGER NOT NULL,
                PRIMARY KEY(entity_id, word));
            CREATE TABLE IF NOT EXISTS tg(
                tag TEXT NOT NULL, id TEXT NOT NULL, type TEXT NOT NULL,
                project TEXT NOT NULL,
                PRIMARY KEY(tag, id));
            CREATE TABLE IF NOT EXISTS tg_et(
                entity_id TEXT NOT NULL, tag TEXT NOT NULL, seq INTEGER NOT NULL,
                PRIMARY KEY(entity_id, tag));
            CREATE TABLE IF NOT EXISTS en(
                id TEXT PRIMARY KEY, project TEXT NOT NULL, type TEXT NOT NULL,
                title TEXT NOT NULL, status TEXT NOT NULL,
                category TEXT NOT NULL, tags_json TEXT NOT NULL,
                updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS rel(
                relation_id TEXT NOT NULL, owner_id TEXT NOT NULL,
                source_id TEXT NOT NULL, target_id TEXT NOT NULL,
                relation_type TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS st(
                key TEXT PRIMARY KEY, count INTEGER NOT NULL);
            """
        )

    # --- Публичный контракт (как IndexStore) ---

    def read(self, project: str, name: str) -> dict[str, Any] | None:
        """Данные индекс-дока (раздел data); None — док отсутствует."""
        if name not in _INDEX_NAMES:
            raise ValueError(f"unknown index name: {name}")
        if not self._db_path(project).exists():
            return None
        con = self._connect(project)
        try:
            present = con.execute(
                "SELECT present FROM meta WHERE name=?", (name,)
            ).fetchone()
            if present is None or not present[0]:
                return None
            return self._read_data(con, name)
        finally:
            con.close()

    def write(self, project: str, name: str, doc: dict[str, Any]) -> None:
        """Записать индекс-док (конверт HKOS-08; полная замена имени)."""
        if name not in _INDEX_NAMES:
            raise ValueError(f"unknown index name: {name}")
        data = doc.get("data")
        if not isinstance(data, dict):
            raise ValueError(f"index doc {name}: missing 'data' section")
        con = self._connect(project)
        try:
            with con:  # одна транзакция на имя
                self._clear_name(con, name)
                self._write_data(con, name, data)
                con.execute(
                    "INSERT INTO meta(name, present) VALUES(?, 1) "
                    "ON CONFLICT(name) DO UPDATE SET present=1",
                    (name,),
                )
        finally:
            con.close()

    def exists(self, project: str, name: str) -> bool:
        """Существует ли индекс-док имени."""
        db_path = self._db_path(project)
        if not db_path.exists():
            return False
        con = self._connect(project)
        try:
            row = con.execute(
                "SELECT present FROM meta WHERE name=?", (name,)
            ).fetchone()
            return bool(row and row[0])
        finally:
            con.close()

    def delete(self, project: str, name: str) -> None:
        """Удалить индекс-док имени (очистить строки + признак)."""
        db_path = self._db_path(project)
        if not db_path.exists():
            return
        con = self._connect(project)
        try:
            with con:
                self._clear_name(con, name)
                con.execute("DELETE FROM meta WHERE name=?", (name,))
        finally:
            con.close()

    def list_names(self, project: str) -> list[str]:
        """Имена существующих индекс-доков проекта."""
        db_path = self._db_path(project)
        if not db_path.exists():
            return []
        con = self._connect(project)
        try:
            rows = con.execute(
                "SELECT name FROM meta WHERE present=1 ORDER BY name"
            ).fetchall()
            return [row[0] for row in rows]
        finally:
            con.close()

    def fingerprint(self, project: str) -> tuple[tuple[str, int, int], ...]:
        """Отпечаток файла БД ((имя, mtime_ns, size)); отсутствует -> -1."""
        path = self._db_path(project)
        try:
            stat = path.stat()
            return ((INDEX_STORE_DB, stat.st_mtime_ns, stat.st_size),)
        except OSError:
            return ((INDEX_STORE_DB, -1, -1),)

    # --- Очистка имени ---

    def _clear_name(self, con: sqlite3.Connection, name: str) -> None:
        """Удалить строки имени (все связанные таблицы)."""
        if name == "keyword":
            con.execute("DELETE FROM kw")
            con.execute("DELETE FROM kw_ew")
        elif name == "tags":
            con.execute("DELETE FROM tg")
            con.execute("DELETE FROM tg_et")
        elif name == "entities":
            con.execute("DELETE FROM en")
        elif name == "relations":
            con.execute("DELETE FROM rel")
        elif name == "statistics":
            con.execute("DELETE FROM st")

    # --- Запись данных (codecs) ---

    def _write_data(
        self, con: sqlite3.Connection, name: str, data: dict[str, Any]
    ) -> None:
        """Записать data-док имени в таблицы (в порядке итерации — важно
        для восстановления порядка списков по rowid)."""
        if name == "keyword":
            self._write_keyword(con, data)
        elif name == "tags":
            self._write_tags(con, data)
        elif name == "entities":
            self._write_entities(con, data)
        elif name == "relations":
            self._write_relations(con, data)
        elif name == "statistics":
            self._write_statistics(con, data)

    @staticmethod
    def _write_keyword(con: sqlite3.Connection, data: dict[str, Any]) -> None:
        postings = data.get("postings", {})
        for word, entries in postings.items():
            for entry in entries:
                con.execute(
                    "INSERT INTO kw(word, id, type, project) VALUES(?,?,?,?)",
                    (word, entry["id"], entry["type"], entry["project"]),
                )
        for seq, (entity_id, words) in enumerate(
            data.get("entity_words", {}).items()
        ):
            for offset, word in enumerate(words):
                con.execute(
                    "INSERT INTO kw_ew(entity_id, word, seq) VALUES(?,?,?)",
                    (entity_id, word, seq * 100_000 + offset),
                )

    @staticmethod
    def _write_tags(con: sqlite3.Connection, data: dict[str, Any]) -> None:
        tags = data.get("tags", {})
        for tag, entries in tags.items():
            for entry in entries:
                con.execute(
                    "INSERT INTO tg(tag, id, type, project) VALUES(?,?,?,?)",
                    (tag, entry["id"], entry["type"], entry["project"]),
                )
        for seq, (entity_id, entity_tags) in enumerate(
            data.get("entity_tags", {}).items()
        ):
            for offset, tag in enumerate(entity_tags):
                con.execute(
                    "INSERT INTO tg_et(entity_id, tag, seq) VALUES(?,?,?)",
                    (entity_id, tag, seq * 100_000 + offset),
                )

    @staticmethod
    def _write_entities(con: sqlite3.Connection, data: dict[str, Any]) -> None:
        entities = data.get("entities", {})
        for entity_id, record in entities.items():
            con.execute(
                "INSERT INTO en(id, project, type, title, status, category,"
                " tags_json, updated_at) VALUES(?,?,?,?,?,?,?,?)",
                (
                    entity_id,
                    record.get("project", ""),
                    record.get("type", ""),
                    record.get("title", ""),
                    record.get("status", ""),
                    record.get("category", ""),
                    json.dumps(record.get("tags", []), ensure_ascii=False),
                    record.get("updated_at", ""),
                ),
            )

    @staticmethod
    def _write_relations(con: sqlite3.Connection, data: dict[str, Any]) -> None:
        entity_relations = data.get("entity_relations", {})
        for owner_id, records in entity_relations.items():
            for record in records:
                con.execute(
                    "INSERT INTO rel(relation_id, owner_id, source_id,"
                    " target_id, relation_type, created_at)"
                    " VALUES(?,?,?,?,?,?)",
                    (
                        record.get("relation_id", ""),
                        owner_id,
                        record.get("source_id", ""),
                        record.get("target_id", ""),
                        record.get("relation_type", ""),
                        record.get("created_at", ""),
                    ),
                )

    @staticmethod
    def _write_statistics(
        con: sqlite3.Connection, data: dict[str, Any]
    ) -> None:
        statistics = data.get("statistics", {})
        for key, count in statistics.items():
            con.execute(
                "INSERT INTO st(key, count) VALUES(?,?)",
                (key, int(count)),
            )

    # --- Чтение данных (реконструкция, порядок по rowid/seq) ---

    def _read_data(
        self, con: sqlite3.Connection, name: str
    ) -> dict[str, Any]:
        """Восстановить data-док из строк (структура = JSON-формат)."""
        if name == "keyword":
            return self._read_keyword(con)
        if name == "tags":
            return self._read_tags(con)
        if name == "entities":
            return self._read_entities(con)
        if name == "relations":
            return self._read_relations(con)
        return self._read_statistics(con)

    @staticmethod
    def _read_keyword(con: sqlite3.Connection) -> dict[str, Any]:
        postings: dict[str, list[dict[str, str]]] = {}
        for row in con.execute(
            "SELECT word, id, type, project FROM kw ORDER BY rowid"
        ):
            postings.setdefault(row[0], []).append({
                "id": row[1], "type": row[2], "project": row[3],
            })
        entity_words: dict[str, list[str]] = {}
        for row in con.execute(
            "SELECT entity_id, word FROM kw_ew ORDER BY seq"
        ):
            entity_words.setdefault(row[0], []).append(row[1])
        return {"postings": postings, "entity_words": entity_words}

    @staticmethod
    def _read_tags(con: sqlite3.Connection) -> dict[str, Any]:
        tags: dict[str, list[dict[str, str]]] = {}
        for row in con.execute(
            "SELECT tag, id, type, project FROM tg ORDER BY rowid"
        ):
            tags.setdefault(row[0], []).append({
                "id": row[1], "type": row[2], "project": row[3],
            })
        entity_tags: dict[str, list[str]] = {}
        for row in con.execute(
            "SELECT entity_id, tag FROM tg_et ORDER BY seq"
        ):
            entity_tags.setdefault(row[0], []).append(row[1])
        return {"tags": tags, "entity_tags": entity_tags}

    @staticmethod
    def _read_entities(con: sqlite3.Connection) -> dict[str, Any]:
        entities: dict[str, dict[str, Any]] = {}
        for row in con.execute(
            "SELECT id, project, type, title, status, category, tags_json,"
            " updated_at FROM en ORDER BY rowid"
        ):
            entities[row[0]] = {
                "id": row[0],
                "project": row[1],
                "type": row[2],
                "title": row[3],
                "status": row[4],
                "category": row[5],
                "tags": json.loads(row[6]),
                "updated_at": row[7],
            }
        return {"entities": entities}

    @staticmethod
    def _read_relations(con: sqlite3.Connection) -> dict[str, Any]:
        rows = con.execute(
            "SELECT rowid, relation_id, owner_id, source_id, target_id,"
            " relation_type, created_at FROM rel ORDER BY rowid"
        ).fetchall()
        out: dict[str, list[dict[str, str]]] = {}
        inn: dict[str, list[dict[str, str]]] = {}
        entity_relations: dict[str, list[dict[str, str]]] = {}
        for row in rows:
            record: dict[str, str] = {
                "relation_id": row[1],
                "source_id": row[3],
                "target_id": row[4],
                "relation_type": row[5],
                "created_at": row[6],
            }
            entity_relations.setdefault(row[2], []).append(record)
            out.setdefault(row[3], []).append(record)
            inn.setdefault(row[4], []).append(record)
        return {"out": out, "in": inn, "entity_relations": entity_relations}

    @staticmethod
    def _read_statistics(con: sqlite3.Connection) -> dict[str, Any]:
        statistics: dict[str, int] = {}
        for row in con.execute("SELECT key, count FROM st"):
            statistics[row[0]] = row[1]
        return {"statistics": statistics}

    @property
    def storage(self) -> StorageEngine:
        """Используемый StorageEngine (как у IndexStore)."""
        return self._storage

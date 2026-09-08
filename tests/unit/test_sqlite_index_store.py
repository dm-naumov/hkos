"""IP-017-v1.2 ЭТАП 1a: SqliteIndexStore — parity с JSON-бэкендом.

Ключевой тест: реальный корпус (knowledge + tags + negative + merge-relations)
индексируется JSON-бэкендом (IndexBuilder); каждый из 5 индекс-доков,
записанный в SqliteIndexStore, читается из SQLite ИДЕНТИЧНО (структура +
порядок списков).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.index import IndexCache, IndexEngine, IndexStore
from hkos.index.sqlite_store import INDEX_STORE_DB, SqliteIndexStore
from hkos.repository.models import Knowledge
from hkos.repository.repository_manager import RepositoryManager
from hkos.services.librarian import Librarian
from hkos.services.project_manager import ProjectManager
from hkos.storage import StorageEngine

_INDEX_NAMES = ("keyword", "tags", "entities", "relations", "statistics")


class SqliteContext:
    """Композиция: JSON-индексы + sqlite-бэкенд на одном data root."""

    def __init__(self, tmp_path: Path) -> None:
        cfg = ConfigLoader(profile="development")
        cfg.load()
        self.engine = StorageEngine(
            root=str(tmp_path), config=cfg, logger=HKOSLogger(),
            version=VersionManager())
        self.engine.initialize()
        self.repos = RepositoryManager(self.engine)
        self.projects = ProjectManager(self.repos, HKOSLogger())
        self.librarian = Librarian(self.repos, HKOSLogger())
        self.json_store = IndexStore(self.engine)
        self.sqlite_store = SqliteIndexStore(self.engine)
        cache = IndexCache()
        self.index = IndexEngine(
            self.repos, self.json_store, HKOSLogger(), cache=cache)

    def build_corpus(self) -> str:
        """Корпус с тегами/negative/merge-relations; JSON-индексы построены."""
        project = self.projects.create(name="P1", tags=["demo"])
        pid = project.id
        a = self.librarian.register(
            pid, Knowledge(
                title="UDP bypasses proxy", body="cause tproxy rule missing",
                tags=["udp", "proxy"]))
        b = self.librarian.register(
            pid, Knowledge(
                title="tproxy rule fixes udp", body="fix routing table",
                tags=["udp", "tproxy"]))
        self.librarian.register(
            pid, Knowledge(
                title="mtu breakage", body="udp dies above 1400",
                kind="negative", tags=["mtu", "udp"]))
        merged = self.librarian.merge(pid, a.id, b.id, reason="duplicate")
        self.index.build(pid)
        assert merged.id
        return pid

    def json_data(self, pid: str, name: str) -> dict[str, object] | None:
        """data индекс-дока из JSON-бэкенда."""
        return self.json_store.read(pid, name)

    def sqlite_data(self, pid: str, name: str) -> dict[str, object] | None:
        """data индекс-дока из sqlite-бэкенда (mirror записан ранее)."""
        return self.sqlite_store.read(pid, name)

    def mirror(self, pid: str, name: str, data: dict[str, object]) -> None:
        """Записать data в sqlite-бэкенд (конверт как _index_doc)."""
        self.sqlite_store.write(pid, name, {
            "schema": "HKOS-1.0", "type": "index", "version": 1,
            "data": data,
        })


class TestSqliteIndexStore:
    """Контракт IndexStore поверх SQLite + parity с JSON."""

    def _ctx(self, tmp_path: Path) -> SqliteContext:
        return SqliteContext(tmp_path)

    def test_parity_all_five_index_docs(self, tmp_path: Path) -> None:
        """Каждый из 5 доков: sqlite.read == json.read (значение)."""
        ctx = self._ctx(tmp_path)
        pid = ctx.build_corpus()
        for name in _INDEX_NAMES:
            json_data = ctx.json_data(pid, name)
            assert json_data is not None, name
            ctx.mirror(pid, name, json_data)
            assert ctx.sqlite_data(pid, name) == json_data, name

    def test_write_replace_leaves_no_stale_rows(self, tmp_path: Path) -> None:
        ctx = self._ctx(tmp_path)
        pid = ctx.build_corpus()
        ctx.mirror(pid, "keyword", ctx.json_data(pid, "keyword") or {})
        # Имитация дельты: запись keyword-дока БЕЗ одного слова/сущности
        reduced_data = ctx.json_data(pid, "keyword")
        assert reduced_data is not None
        reduced = dict(reduced_data)
        postings = reduced["postings"]
        entity_words = reduced["entity_words"]
        assert isinstance(postings, dict) and isinstance(entity_words, dict)
        removed_word = next(iter(postings))
        del postings[removed_word]
        removed_entity = next(iter(entity_words))
        del entity_words[removed_entity]
        ctx.mirror(pid, "keyword", reduced)
        read_back = ctx.sqlite_data(pid, "keyword")
        assert read_back is not None and read_back == reduced
        read_postings = read_back["postings"]
        read_entity_words = read_back["entity_words"]
        assert isinstance(read_postings, dict)
        assert isinstance(read_entity_words, dict)
        assert removed_word not in read_postings
        assert removed_entity not in read_entity_words

    def test_missing_and_delete_semantics(self, tmp_path: Path) -> None:
        ctx = self._ctx(tmp_path)
        pid = ctx.build_corpus()
        # Несуществующий проект/док -> None
        assert ctx.sqlite_data("no-such-project", "keyword") is None
        empty = self._ctx(tmp_path / "other").projects.create(
            name="E", tags=[]).id
        assert ctx.sqlite_store.list_names(empty) == []
        # delete(name): док исчезает, остальные живы
        ctx.mirror(pid, "statistics", ctx.json_data(pid, "statistics") or {})
        assert ctx.sqlite_store.exists(pid, "statistics")
        ctx.sqlite_store.delete(pid, "statistics")
        assert not ctx.sqlite_store.exists(pid, "statistics")
        assert ctx.sqlite_data(pid, "statistics") is None
        assert "statistics" not in ctx.sqlite_store.list_names(pid)

    def test_wal_journal_mode(self, tmp_path: Path) -> None:
        ctx = self._ctx(tmp_path)
        pid = ctx.build_corpus()
        ctx.mirror(pid, "entities", ctx.json_data(pid, "entities") or {})
        db_path = (Path(ctx.engine.root) / "projects" / pid / "indexes"
                   / INDEX_STORE_DB)
        con = sqlite3.connect(str(db_path))
        try:
            assert con.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        finally:
            con.close()

    def test_project_isolation(self, tmp_path: Path) -> None:
        ctx = self._ctx(tmp_path)
        pid1 = ctx.projects.create(name="A", tags=[]).id
        pid2 = ctx.projects.create(name="B", tags=[]).id
        data = {"postings": {"w1": [{"id": "x", "type": "knowledge",
                                     "project": pid1}]},
                "entity_words": {"x": ["w1"]}}
        ctx.mirror(pid1, "keyword", data)
        assert ctx.sqlite_data(pid2, "keyword") is None
        # физически разные файлы
        db1 = Path(ctx.engine.root) / "projects" / pid1 / "indexes" / INDEX_STORE_DB
        db2 = Path(ctx.engine.root) / "projects" / pid2 / "indexes" / INDEX_STORE_DB
        assert db1.exists() and not db2.exists()

    def test_reopen_reads_same_data(self, tmp_path: Path) -> None:
        ctx = self._ctx(tmp_path)
        pid = ctx.build_corpus()
        for name in _INDEX_NAMES:
            ctx.mirror(pid, name, ctx.json_data(pid, name) or {})
        # новое соединение (новый экземпляр store)
        reopened = SqliteIndexStore(ctx.engine)
        for name in _INDEX_NAMES:
            assert reopened.read(pid, name) == ctx.json_data(pid, name), name

    def test_fingerprint_stable_then_changes(self, tmp_path: Path) -> None:
        ctx = self._ctx(tmp_path)
        pid = ctx.build_corpus()
        # До первой записи в sqlite файла БД нет -> (-1, -1)
        fp_missing = ctx.sqlite_store.fingerprint(pid)
        assert fp_missing == ((INDEX_STORE_DB, -1, -1),)
        ctx.mirror(pid, "entities", ctx.json_data(pid, "entities") or {})
        fp1 = ctx.sqlite_store.fingerprint(pid)
        fp2 = ctx.sqlite_store.fingerprint(pid)
        assert fp1 == fp2 and fp1[0][0] == INDEX_STORE_DB and fp1[0][1] > 0
        ctx.mirror(pid, "keyword", ctx.json_data(pid, "keyword") or {})
        fp3 = ctx.sqlite_store.fingerprint(pid)
        assert fp3 != fp1
        missing = ctx.sqlite_store.fingerprint("no-such")
        assert missing == ((INDEX_STORE_DB, -1, -1),)

    def test_stable_roundtrip(self, tmp_path: Path) -> None:
        """write→read→write даёт стабильные данные (идемпотентность)."""
        ctx = self._ctx(tmp_path)
        pid = ctx.build_corpus()
        for name in _INDEX_NAMES:
            data = ctx.json_data(pid, name)
            assert data is not None
            ctx.mirror(pid, name, data)
            first = ctx.sqlite_data(pid, name)
            assert first is not None
            ctx.mirror(pid, name, first)  # read→write повторно
            assert ctx.sqlite_data(pid, name) == first

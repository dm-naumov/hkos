"""IP-017-v1.2 ЭТАП 1a: SqliteIndexStore — parity с JSON-бэкендом.

Ключевой тест: реальный корпус (knowledge + tags + negative + merge-relations)
индексируется JSON-бэкендом (IndexBuilder); каждый из 5 индекс-доков,
записанный в SqliteIndexStore, читается из SQLite ИДЕНТИЧНО (структура +
порядок списков).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from hkos.core.config import ConfigLoader
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.index import (
    IndexCache,
    IndexEngine,
    IndexQueryExecutor,
    IndexStore,
)
from hkos.index.sqlite_store import INDEX_STORE_DB, SqliteIndexStore
from hkos.repository.models import Knowledge
from hkos.repository.repository_manager import RepositoryManager
from hkos.retrieval import RetrievalEngine
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
        return self.json_store.read(pid, name)

    def sqlite_data(self, pid: str, name: str) -> dict[str, object] | None:
        return self.sqlite_store.read(pid, name)

    def mirror(self, pid: str, name: str, data: dict[str, object]) -> None:
        self.sqlite_store.write(pid, name, {
            "schema": "HKOS-1.0", "type": "index", "version": 1,
            "data": data,
        })


class TestSqliteIndexStore:
    def _ctx(self, tmp_path: Path) -> SqliteContext:
        return SqliteContext(tmp_path)

    def test_parity_all_five_index_docs(self, tmp_path: Path) -> None:
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
        assert ctx.sqlite_data("no-such-project", "keyword") is None
        empty = self._ctx(tmp_path / "other").projects.create(
            name="E", tags=[]).id
        assert ctx.sqlite_store.list_names(empty) == []
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
        db1 = Path(ctx.engine.root) / "projects" / pid1 / "indexes" / INDEX_STORE_DB
        db2 = Path(ctx.engine.root) / "projects" / pid2 / "indexes" / INDEX_STORE_DB
        assert db1.exists() and not db2.exists()

    def test_reopen_reads_same_data(self, tmp_path: Path) -> None:
        ctx = self._ctx(tmp_path)
        pid = ctx.build_corpus()
        for name in _INDEX_NAMES:
            ctx.mirror(pid, name, ctx.json_data(pid, name) or {})
        reopened = SqliteIndexStore(ctx.engine)
        for name in _INDEX_NAMES:
            assert reopened.read(pid, name) == ctx.json_data(pid, name), name

    def test_fingerprint_stable_then_changes(self, tmp_path: Path) -> None:
        ctx = self._ctx(tmp_path)
        pid = ctx.build_corpus()
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
        ctx = self._ctx(tmp_path)
        pid = ctx.build_corpus()
        for name in _INDEX_NAMES:
            data = ctx.json_data(pid, name)
            assert data is not None
            ctx.mirror(pid, name, data)
            first = ctx.sqlite_data(pid, name)
            assert first is not None
            ctx.mirror(pid, name, first)
            assert ctx.sqlite_data(pid, name) == first


class TestSqliteDeltaUpdate:
    def test_incremental_ops_match_json(self, tmp_path: Path) -> None:
        ctx = SqliteContext(tmp_path)
        pid = ctx.projects.create(name="Delta", tags=["t"]).id

        def register(title: str, body: str, tags: list[str],
                     kind: str = "fact") -> str:
            k = ctx.librarian.register(pid, Knowledge(
                title=title, body=body, tags=tags, kind=kind))
            ctx.index.update(pid, k.id, "knowledge")
            ctx.sqlite_store.update_entity(
                pid, ctx.repos.knowledge.load(pid, k.id), "knowledge")
            return k.id

        a = register("udp tproxy fix", "routing table fwmark", ["udp", "t"])
        register("udp breakage mtu", "mtu 1400 kills udp", ["udp", "mtu"],
                 kind="negative")
        _assert_all_equal(ctx, pid)
        changed = ctx.repos.knowledge.load(pid, a)
        changed.body = "completely different body dns"
        changed.tags = ["dns"]
        ctx.repos.knowledge.update(changed)
        fresh = ctx.repos.knowledge.load(pid, a)
        ctx.index.update(pid, a, "knowledge")
        ctx.sqlite_store.update_entity(pid, fresh, "knowledge")
        _assert_all_equal(ctx, pid)
        ctx.index.remove(pid, a, "knowledge")
        ctx.sqlite_store.remove_entity(pid, a, "knowledge")
        _assert_all_equal(ctx, pid)

    def test_statistics_delta_counts(self, tmp_path: Path) -> None:
        ctx = SqliteContext(tmp_path)
        pid = ctx.projects.create(name="Stats", tags=["t"]).id
        k1 = ctx.librarian.register(pid, Knowledge(title="one udp fact", body="a"))
        k2 = ctx.librarian.register(pid, Knowledge(title="two udp fact", body="b"))
        k3 = ctx.librarian.register(
            pid, Knowledge(title="three negative udp", body="c", kind="negative"))
        for k in (k1, k2, k3):
            ctx.sqlite_store.update_entity(
                pid, ctx.repos.knowledge.load(pid, k.id), "knowledge")
        stats = ctx.sqlite_data(pid, "statistics")
        assert stats is not None
        stats_statistics = stats["statistics"]
        assert isinstance(stats_statistics, dict)
        counts = stats_statistics
        assert counts["knowledge"] == 3 and counts["decisions"] == 0
        ctx.sqlite_store.remove_entity(pid, k3.id, "knowledge")
        stats2 = ctx.sqlite_data(pid, "statistics")
        assert stats2 is not None
        stats2_statistics = stats2["statistics"]
        assert isinstance(stats2_statistics, dict)
        assert stats2_statistics["knowledge"] == 2


def _assert_all_equal(ctx: SqliteContext, pid: str) -> None:
    for name in _INDEX_NAMES:
        json_data = ctx.json_data(pid, name)
        assert json_data is not None, name
        assert ctx.sqlite_data(pid, name) == json_data, name


class TestSqliteQueryLayer:
    def test_query_snapshot_matches_json(self, tmp_path: Path) -> None:
        ctx = SqliteContext(tmp_path)
        pid = ctx.build_corpus()
        for name in _INDEX_NAMES:
            ctx.mirror(pid, name, ctx.json_data(pid, name) or {})
        json_qc = IndexQueryExecutor(ctx.json_store)
        sqlite_qc = IndexQueryExecutor(ctx.sqlite_store)
        js = json_qc.snapshot(pid)
        ss = sqlite_qc.snapshot(pid)
        assert ss.keyword_search("udp") == js.keyword_search("udp")
        assert ss.keyword_search("mtu") == js.keyword_search("mtu")
        assert ss.keyword_search("absent-word") == []
        assert ss.tag_search("tproxy") == js.tag_search("tproxy")
        for eid in js.ids():
            assert ss.entity_get(eid) == js.entity_get(eid)
        assert ss.entity_get("no-such-id") is None

        def canon(rels: list[Any]) -> list[dict[str, str]]:
            return sorted(
                (r.to_dict() for r in rels),
                key=lambda d: (d["created_at"], d["relation_id"]),
            )

        for eid in js.ids():
            assert canon(ss.relations_of_knowledge(eid)) == canon(
                js.relations_of_knowledge(eid)
            ), eid
        assert canon(ss.relations_of_project()) == canon(
            js.relations_of_project()
        )
        assert ss.statistics() == js.statistics()
        assert ss.ids() == js.ids()

    def test_hot_path_sqlite_backend_retrieval(
        self, tmp_path: Path
    ) -> None:
        cfg = ConfigLoader(profile="development")
        cfg.load()
        engine = StorageEngine(
            root=str(tmp_path), config=cfg, logger=HKOSLogger(),
            version=VersionManager())
        engine.initialize()
        repos = RepositoryManager(engine)
        projects = ProjectManager(repos, HKOSLogger())
        librarian = Librarian(repos, HKOSLogger())
        sqlite_store = SqliteIndexStore(engine)
        index = IndexEngine(repos, sqlite_store, HKOSLogger())
        qc = IndexQueryExecutor(sqlite_store)
        retrieval = RetrievalEngine(repos, qc, cfg, HKOSLogger())

        pid = projects.create(name="P1", tags=["demo"]).id
        titles: list[str] = []
        for title, body, tags in [
            ("UDP bypasses proxy", "cause tproxy rule missing",
             ["udp", "proxy"]),
            ("tproxy rule fixes udp", "fix routing table",
             ["udp", "tproxy"]),
            ("mtu breakage", "udp dies above 1400",
             ["mtu", "udp"]),
        ]:
            k = librarian.register(
                pid, Knowledge(title=title, body=body, tags=tags))
            librarian.canonicalize(pid, k.id)
            index.update(pid, k.id, "knowledge")
            titles.append(title)

        result = retrieval.retrieve("udp", project_id=pid, top_n=10)
        got = sorted(item.entity.title for item in result.items)
        assert got == sorted(titles), f"hot path misses knowledge: {got}"
        snap = qc.snapshot(pid)
        assert sorted(snap.ids()) == sorted(
            item.entity.id for item in result.items)
        assert snap.statistics()["knowledge"] == len(titles)

    def test_hot_path_update_is_delta(self, tmp_path: Path) -> None:
        ctx = SqliteContext(tmp_path)
        pid = ctx.build_corpus()
        for name in _INDEX_NAMES:
            ctx.mirror(pid, name, ctx.json_data(pid, name) or {})
        sqlite_index = IndexEngine(
            ctx.repos, ctx.sqlite_store, HKOSLogger())
        kw_before = ctx.sqlite_store.read(pid, "keyword")
        assert kw_before is not None
        postings_before = kw_before["postings"]
        assert isinstance(postings_before, dict)
        rows_before = sum(len(v) for v in postings_before.values())

        k = ctx.librarian.register(
            pid, Knowledge(
                title="new knowledge entry", body="fresh body words",
                tags=["fresh"]))
        sqlite_index.update(pid, k.id, "knowledge")
        kw_after = ctx.sqlite_store.read(pid, "keyword")
        assert kw_after is not None
        postings_after = kw_after["postings"]
        assert isinstance(postings_after, dict)
        rows_after = sum(len(v) for v in postings_after.values())
        assert rows_after > rows_before
        assert len(postings_after) - len(postings_before) < 10
        sqlite_index.remove(pid, k.id, "knowledge")
        kw_final = ctx.sqlite_store.read(pid, "keyword")
        assert kw_final is not None
        postings_final = kw_final["postings"]
        assert isinstance(postings_final, dict)
        rows_final = sum(len(v) for v in postings_final.values())
        assert rows_final == rows_before

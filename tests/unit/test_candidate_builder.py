"""Unit tests for CandidateBuilder (DS-008 §9, IP-008)."""

from hkos.index.query_contract import EntityRecord, IndexEntry
from hkos.retrieval.candidate_builder import CandidateBuilder
from hkos.retrieval.query_parser import ParsedQuery


class FakeQuery:
    """In-memory снимок Query Contract (IndexSnapshot-аналог) для тестов."""

    def __init__(self) -> None:
        self.keyword_calls: list[str] = []
        self.tag_calls: list[str] = []
        self.entity_calls: list[str] = []
        self.relation_calls: list[str] = []

    def keyword_search(self, word: str) -> list[IndexEntry]:
        self.keyword_calls.append(word)
        if word == "udp":
            return [IndexEntry(id="k1", type="knowledge", project="p1")]
        if word == "tproxy":
            return [IndexEntry(id="k2", type="knowledge", project="p1")]
        return []

    def tag_search(self, tag: str) -> list[IndexEntry]:
        self.tag_calls.append(tag)
        if tag == "udp":
            return [IndexEntry(id="k3", type="knowledge", project="p1")]
        return []

    def entity_get(self, entity_id: str) -> EntityRecord | None:
        self.entity_calls.append(entity_id)
        if entity_id == "k-known":
            return EntityRecord(id="k-known", project="p1", type="knowledge", title="Known")
        return None

    def relations_of_knowledge(self, knowledge_id: str) -> list[object]:
        self.relation_calls.append(knowledge_id)
        return []

    def relations_of_project(self) -> list[object]:
        return []

    def statistics(self) -> dict[str, int]:
        return {"knowledge": 0, "decisions": 0, "campaigns": 0, "projects": 0, "artifacts": 0}


class TestCandidateBuilder:
    """Сбор кандидатов только через Query Contract."""

    def test_keyword_stage(self) -> None:
        query = FakeQuery()
        builder = CandidateBuilder()
        parsed = ParsedQuery(keywords=["udp"])
        result = builder.build(parsed, "p1", query)
        assert query.keyword_calls == ["udp"]
        assert [e.id for e in result.entries] == ["k1"]

    def test_tag_stage(self) -> None:
        query = FakeQuery()
        builder = CandidateBuilder()
        parsed = ParsedQuery(topic="udp")
        result = builder.build(parsed, "p1", query)
        assert query.tag_calls == ["udp"]
        assert [e.id for e in result.entries] == ["k3"]

    def test_entity_stage(self) -> None:
        query = FakeQuery()
        builder = CandidateBuilder()
        parsed = ParsedQuery(keywords=["k-known"])
        result = builder.build(parsed, "p1", query)
        assert "k-known" in [e.id for e in result.entries]

    def test_merge_dedup(self) -> None:
        query = FakeQuery()
        builder = CandidateBuilder()
        parsed = ParsedQuery(keywords=["udp", "tproxy"])
        result = builder.build(parsed, "p1", query)
        ids = [e.id for e in result.entries]
        assert len(ids) == len(set(ids))

    def test_project_filter(self) -> None:
        query = FakeQuery()
        builder = CandidateBuilder()
        parsed = ParsedQuery(keywords=["udp"])
        result = builder.build(parsed, "other-project", query)
        assert result.entries == []  # k1 в p1, фильтр по другому проекту

    def test_max_candidates_cap(self) -> None:
        query = FakeQuery()
        builder = CandidateBuilder(max_candidates=1)
        parsed = ParsedQuery(keywords=["udp", "tproxy"])
        result = builder.build(parsed, "p1", query)
        assert len(result.entries) <= 1

    def test_sources_tracked(self) -> None:
        query = FakeQuery()
        builder = CandidateBuilder()
        parsed = ParsedQuery(keywords=["udp"], topic="udp")
        result = builder.build(parsed, "p1", query)
        # k1 из keyword:udp; k3 из tag:udp
        assert "keyword:udp" in result.sources.get("k1", [])
        assert "tag:udp" in result.sources.get("k3", [])

    def test_only_query_contract_called(self) -> None:
        """Builder не вызывает ничего, кроме Query Contract."""
        query = FakeQuery()
        builder = CandidateBuilder()
        builder.build(ParsedQuery(keywords=["udp"]), "p1", query)
        assert query.entity_calls or query.keyword_calls or query.tag_calls

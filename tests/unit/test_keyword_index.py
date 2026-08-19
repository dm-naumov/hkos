"""Unit tests for KeywordIndex (DS-007 §7)."""

from hkos.index.keyword_index import KeywordIndex, indexable_text
from hkos.repository.models import Knowledge


class TestKeywordIndex:
    """Keyword Index: токенизация, add/remove/search."""

    def test_tokenize(self) -> None:
        assert KeywordIndex.tokenize("TProxy UDP works") == ["tproxy", "udp", "works"]

    def test_tokenize_short_words_filtered(self) -> None:
        assert KeywordIndex.tokenize("a bb ccc") == ["bb", "ccc"]

    def test_tokenize_dedup(self) -> None:
        assert KeywordIndex.tokenize("udp udp tcp") == ["tcp", "udp"]

    def test_indexable_text_knowledge(self) -> None:
        k = Knowledge(title="TProxy", body="udp", category="FACT", kind="fact")
        text = indexable_text(k).lower()
        assert "tproxy" in text
        assert "udp" in text
        assert "fact" in text

    def test_add_and_search(self) -> None:
        index = KeywordIndex()
        index.add("k1", "knowledge", "p1", "TProxy UDP works")
        results = index.search("tproxy")
        assert len(results) == 1
        assert results[0]["id"] == "k1"
        assert results[0]["type"] == "knowledge"

    def test_add_dedup_entries(self) -> None:
        index = KeywordIndex()
        index.add("k1", "knowledge", "p1", "tproxy tproxy")
        assert len(index.search("tproxy")) == 1

    def test_remove_cleans_postings(self) -> None:
        index = KeywordIndex()
        index.add("k1", "knowledge", "p1", "TProxy UDP")
        index.add("k2", "knowledge", "p1", "TProxy nft")
        index.remove("k1")
        results = index.search("tproxy")
        assert [r["id"] for r in results] == ["k2"]
        assert "udp" not in [w for w in index.data()["postings"]]

    def test_entity_words_tracked(self) -> None:
        index = KeywordIndex()
        index.add("k1", "knowledge", "p1", "udp traffic")
        assert set(index.entity_words("k1")) == {"udp", "traffic"}

    def test_search_missing_word(self) -> None:
        assert KeywordIndex().search("nope") == []

    def test_word_count(self) -> None:
        index = KeywordIndex()
        index.add("k1", "knowledge", "p1", "udp traffic")
        index.add("k2", "knowledge", "p1", "udp dns")
        assert index.word_count() == 3  # udp, traffic, dns

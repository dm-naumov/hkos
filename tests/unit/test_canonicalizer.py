"""Unit tests for Canonicalizer (DS-006 §10, IP-006 §4)."""

from hkos.repository.models import Knowledge
from hkos.services.librarian.canonicalizer import Canonicalizer


class TestCanonicalizer:
    """Canonicalizer работает только с переданным набором (без Repository)."""

    def test_normalize(self) -> None:
        assert Canonicalizer.normalize("  TProxy   UDP  ") == "tproxy udp"

    def test_exact_duplicate(self) -> None:
        a = Knowledge(id="1", title="TProxy UDP works")
        b = Knowledge(id="2", title="tproxy udp works")
        assert Canonicalizer.is_duplicate(a, b) is True

    def test_different_titles_not_duplicate(self) -> None:
        a = Knowledge(id="1", title="TProxy UDP works")
        b = Knowledge(id="2", title="TProxy TCP works")
        assert Canonicalizer.is_duplicate(a, b) is False

    def test_find_duplicates_in_set(self) -> None:
        candidate = Knowledge(id="1", title="TProxy UDP works")
        others = [
            Knowledge(id="2", title="tproxy  udp  works"),
            Knowledge(id="3", title="Other topic"),
        ]
        found = Canonicalizer.find_duplicates(candidate, others)
        assert [k.id for k in found] == ["2"]

    def test_find_duplicates_excludes_self(self) -> None:
        candidate = Knowledge(id="1", title="Same")
        others = [Knowledge(id="1", title="Same")]
        assert Canonicalizer.find_duplicates(candidate, others) == []

    def test_empty_title_no_duplicates(self) -> None:
        candidate = Knowledge(id="1", title="")
        others = [Knowledge(id="2", title="")]
        assert Canonicalizer.find_duplicates(candidate, others) == []

    def test_works_without_repository(self) -> None:
        """Canonicalizer — чистые функции; нет зависимости от Repository."""
        import inspect

        source = inspect.getsource(Canonicalizer)
        assert "repository" not in source.lower()

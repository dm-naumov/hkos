"""Unit tests for CategoryMergePolicy (DS-006A §6)."""

from hkos.services.librarian.category_merge import CategoryMergePolicy


class TestCategoryMergePolicy:
    """Политика выбора категории объединённого Knowledge."""

    def test_first_wins(self) -> None:
        assert CategoryMergePolicy.resolve("FACT", "FAILURE") == "FACT"

    def test_fallback_to_second(self) -> None:
        assert CategoryMergePolicy.resolve("", "RULE") == "RULE"

    def test_both_empty(self) -> None:
        assert CategoryMergePolicy.resolve("", "") == ""

    def test_matches_previous_behavior(self) -> None:
        """Политика = a.category or b.category (поведение DS-006)."""
        assert CategoryMergePolicy.resolve("A", "B") == ("A" or "B")
        assert CategoryMergePolicy.resolve("", "B") == ("" or "B")

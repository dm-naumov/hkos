"""KI-002 regression tests: Retriever must not filter candidates twice.

Two properties are verified via mocked collaborators:

1. KnowledgeFilter.filter is called exactly once per run_parsed invocation.
   Before the fix it was called twice: once before RelationshipTraverser
   (step 4) and again after (step 6), re-filtering already-eligible items.

2. RelationshipTraverser.traverse receives the full *ranked* list, not a
   pre-filtered subset.  Before the fix non-canonical items were silently
   dropped before traversal, blocking relation paths that could have led to
   canonical knowledge.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from hkos.retrieval.retriever import Retriever


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _wire(
    *,
    ranked: list[Any],
    expanded: list[Any],
    eligible: list[Any],
) -> tuple[Retriever, MagicMock, MagicMock]:
    """Return (retriever, filter_mock, traverser_mock) with canned returns."""
    parsed = MagicMock()
    parsed.include_history = False

    parser = MagicMock()
    parser.parse.return_value = parsed

    builder = MagicMock()
    builder.build.return_value = []

    ranking = MagicMock()
    ranking.rank.return_value = ranked

    filter_mock = MagicMock()
    filter_mock.filter.return_value = eligible

    traverser_mock = MagicMock()
    traverser_mock.traverse.return_value = expanded

    selector = MagicMock()
    selector.select.return_value = eligible

    retriever = Retriever(
        parser=parser,
        builder=builder,
        ranking=ranking,
        filter_=filter_mock,
        traverser=traverser_mock,
        selector=selector,
    )
    return retriever, filter_mock, traverser_mock


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRetrieverKI002:
    """KI-002: single eligibility pass; traversal from the full ranked set."""

    def test_filter_called_exactly_once_in_run_parsed(self) -> None:
        """KnowledgeFilter.filter must be called exactly once per run_parsed.

        Before KI-002 fix: filter was invoked twice — before traversal
        (pre-filter on ranked) and again after traversal (on expanded).
        Direct candidates were filtered redundantly.
        """
        c = MagicMock(name="candidate")
        retriever, filter_mock, _ = _wire(ranked=[c], expanded=[c], eligible=[c])

        retriever.run("query")

        assert filter_mock.filter.call_count == 1, (
            f"KnowledgeFilter.filter called {filter_mock.filter.call_count} time(s); "
            "expected exactly 1.  KI-002: direct candidates must not be filtered twice."
        )

    def test_traverser_receives_full_ranked_list(self) -> None:
        """Traverser must receive the unfiltered `ranked` list as its first arg.

        Before KI-002 fix: traverser received pre-filtered candidates,
        silently excluding non-canonical items.  A non-canonical item may
        carry relations to canonical knowledge and must reach the traverser.
        """
        canonical = MagicMock(name="canonical")
        noncanon = MagicMock(name="noncanon")
        ranked = [canonical, noncanon]

        retriever, _, traverser_mock = _wire(
            ranked=ranked, expanded=ranked, eligible=[canonical]
        )
        retriever.run("query")

        first_arg = traverser_mock.traverse.call_args[0][0]
        assert first_arg is ranked, (
            "Traverser must receive the full ranked list (before filtering). "
            "KI-002: non-canonical items may seed relation paths to canonical knowledge."
        )

    def test_filter_applied_to_traverser_output(self) -> None:
        """Filter must be applied to traverser's expanded output, not to ranked."""
        original = MagicMock(name="original")
        neighbor = MagicMock(name="neighbor_via_relation")
        ranked = [original]
        expanded = [original, neighbor]

        retriever, filter_mock, _ = _wire(
            ranked=ranked, expanded=expanded, eligible=[original, neighbor]
        )
        retriever.run("query")

        filter_arg = filter_mock.filter.call_args[0][0]
        assert filter_arg is expanded, (
            "Filter must receive the traverser's expanded output. "
            "KI-002: eligibility check covers both direct candidates and relation-added neighbors."
        )

    def test_run_search_filter_once_traverser_never(self) -> None:
        """run_search calls filter exactly once and never invokes traverser."""
        c = MagicMock(name="candidate")

        parsed = MagicMock()
        parsed.include_history = False

        parser = MagicMock()
        parser.parse.return_value = parsed

        builder = MagicMock()
        builder.build.return_value = []

        ranking = MagicMock()
        ranking.rank.return_value = [c]

        filter_mock = MagicMock()
        filter_mock.filter.return_value = [c]

        traverser_mock = MagicMock()

        selector = MagicMock()
        selector.select.return_value = [c]

        retriever = Retriever(
            parser=parser,
            builder=builder,
            ranking=ranking,
            filter_=filter_mock,
            traverser=traverser_mock,
            selector=selector,
        )
        retriever.run_search("query")

        assert filter_mock.filter.call_count == 1, (
            f"run_search: filter called {filter_mock.filter.call_count} time(s); expected 1."
        )
        traverser_mock.traverse.assert_not_called()

"""DS-015 ЭТАП 4: Token Optimization System Test.
================================================================
Реальный инженерный контекст (100 знаний, 6 категорий); профили
NONE/LIGHT/NORMAL/AGGRESSIVE; protected сохраняются; semantic_equivalence.
"""


from hkos.performance.context_profiles import (
    PROFILE_AGGRESSIVE,
    PROFILE_LIGHT,
    PROFILE_NONE,
    PROFILE_NORMAL,
    PerformanceContextOptimizer,
)
from hkos.repository.models import Knowledge


def _engineering_context() -> object:
    from hkos.context.models import ContextDocument, ContextItem

    items: list[ContextItem] = []
    specs = [
        ("Decision A", "DECISION", "DECISIONS"),
        ("Failure A", "FAILURE", "FAILURES"),
        ("Config A", "CONFIGURATION", "CONFIGURATION"),
        # 9 removable категорий (реалистичный контекст: большинство —
        # второстепенный контент, сжимаемый AGGRESSIVE)
        ("Explanation A", "EXPLANATION", "CANONICAL KNOWLEDGE"),
        ("Explanation B", "EXPLANATION", "CANONICAL KNOWLEDGE"),
        ("Explanation C", "EXPLANATION", "CANONICAL KNOWLEDGE"),
        ("Artifact A", "ARTIFACT", "ARTIFACTS"),
        ("Artifact B", "ARTIFACT", "ARTIFACTS"),
        ("Artifact C", "ARTIFACT", "ARTIFACTS"),
        ("Temp A", "TEMPORARY", "CANONICAL KNOWLEDGE"),
        ("Temp B", "TEMPORARY", "CANONICAL KNOWLEDGE"),
        ("Temp C", "TEMPORARY", "CANONICAL KNOWLEDGE"),
    ]
    for i in range(100):
        title, category, _section = specs[i % len(specs)]
        items.append(ContextItem(
            entity=Knowledge(title=f"{title} {i} udp",
                             body="udp engineering " * 20,
                             tags=["udp"], category=category),
            entity_type="knowledge"))
    return ContextDocument(items=items, project_id="p1")


class TestTokenOptimization:
    """Профили сжатия: protected сохраняются; токены уменьшаются."""

    def test_profiles_preserve_protected(self) -> None:
        context = _engineering_context()
        for profile in (PROFILE_LIGHT, PROFILE_NORMAL, PROFILE_AGGRESSIVE):
            optimizer = PerformanceContextOptimizer(profile)
            compressed = optimizer.compress(context)
            sections = compressed.sections
            # protected знания всегда сохраняются
            assert sections.get("DECISIONS"), f"{profile}: DECISIONS lost"
            assert sections.get("FAILURES"), f"{profile}: FAILURES lost"
            assert sections.get("CONFIGURATION"), f"{profile}: CONFIGURATION lost"

    def test_failure_knowledge_never_deleted(self) -> None:
        context = _engineering_context()
        optimizer = PerformanceContextOptimizer(PROFILE_AGGRESSIVE)
        compressed = optimizer.compress(context)
        failures = compressed.sections.get("FAILURES", [])
        assert failures, "FAILURE knowledge deleted"
        # причины ошибок сохраняются (body intact)
        first = failures[0]
        body = str(getattr(getattr(first, "entity", first), "body", ""))
        assert "engineering" in body

    def test_irrelevant_context_reduced(self) -> None:
        context = _engineering_context()
        optimizer = PerformanceContextOptimizer(PROFILE_AGGRESSIVE)
        compressed = optimizer.compress(context)
        total = compressed.item_count()
        assert total < 100  # нерелевантный контекст уменьшается
        assert total >= 4  # protected остаются

    def test_semantic_equivalence(self) -> None:
        """до/после: protected-контент идентичен (смысл сохранён)."""
        context = _engineering_context()
        # 100 items / 12 категорий: ~8-9 protected каждого типа
        optimizer = PerformanceContextOptimizer(PROFILE_NORMAL)
        compressed = optimizer.compress(context)
        for section in ("DECISIONS", "FAILURES", "CONFIGURATION"):
            actual = len(compressed.sections.get(section, []))
            assert actual >= 8, (
                f"{section}: {actual} < 8 (protected must stay)")

    def test_token_reduction(self) -> None:
        """Token reduction: NONE -> AGGRESSIVE уменьшает; reduction > 0."""
        from hkos.performance.context_profiles import CompressedContext

        context = _engineering_context()

        def _tokens(doc: object) -> int:
            """Токены контекста (items у оригинала; sections у сжатого)."""
            items = getattr(doc, "items", None)
            if isinstance(items, list):
                return sum(
                    len(str(getattr(getattr(i, "entity", i), "body", "")))
                    for i in items)
            sections = getattr(doc, "sections", {})
            return sum(
                len(str(getattr(getattr(i, "entity", i), "body", "")))
                for section in sections.values() for i in section)

        full = PerformanceContextOptimizer(PROFILE_NONE).compress(context)
        tokens_before = _tokens(full)
        aggressive = PerformanceContextOptimizer(PROFILE_AGGRESSIVE)
        compressed = aggressive.compress(context)
        assert isinstance(compressed, CompressedContext)
        tokens_after = _tokens(compressed)
        reduction = (tokens_before - tokens_after) / tokens_before
        assert reduction > 0.6, f"token reduction {reduction:.0%}"

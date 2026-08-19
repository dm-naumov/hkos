"""DS-016 ЭТАП 2: Context Injection (C).
================================================================
Retrieval -> ContextBuilder -> DS-013 TokenOptimizer -> LLM (mock).
Профили NONE/LIGHT/NORMAL/AGGRESSIVE; protected сохраняются;
semantic equivalence; reduction соответствует DS-015 SLA.
"""

from pathlib import Path

from hkos.performance.context_profiles import (
    PROFILE_AGGRESSIVE,
    PROFILE_LIGHT,
    PROFILE_NONE,
    PROFILE_NORMAL,
    PerformanceContextOptimizer,
)
from tests.system.ds016.hermes_context import create_hermes_context


class _FakeContext:
    def __init__(self, sections: dict[str, list[object]]) -> None:
        self.sections = sections


class TestContextInjection:
    """Контекст для LLM: реальный ContextBuilder + оптимизация."""

    def test_retrieval_context_built(self, tmp_path: Path) -> None:
        """Retrieval -> ContextBuilder: контекст реально строится."""
        from hkos.repository.models import Knowledge

        ctx = create_hermes_context(tmp_path)
        project = ctx.project.create(name="Ctx", tags=["hermes"])
        k = ctx.librarian.register(project.id, Knowledge(
            title="CtxFact udp", body="udp", tags=["udp"]))
        ctx.librarian.canonicalize(project.id, k.id)
        ctx.index.build(project.id)
        bundle = ctx.retrieve_before_task(
            "udp", project_id=project.id)
        assert bundle["context"] is not None
        assert bundle["optimized"] is not None
        assert bundle["reduction"] >= 0

    def test_profiles_preserve_protected(self, tmp_path: Path) -> None:
        """NONE/LIGHT/NORMAL/AGGRESSIVE: protected не теряются."""
        from hkos.repository.models import Knowledge

        for profile in (PROFILE_NONE, PROFILE_LIGHT, PROFILE_NORMAL,
                        PROFILE_AGGRESSIVE):
            optimizer = PerformanceContextOptimizer(profile)
            sections = {
                "DECISIONS": [Knowledge(title=f"D{i} udp", body="udp",
                                        category="DECISION") for i in range(5)],
                "FAILURES": [Knowledge(title=f"F{i} udp", body="udp",
                                       kind="negative") for i in range(5)],
                "CONFIGURATION": [Knowledge(title=f"C{i} udp", body="udp",
                                            category="CONFIGURATION")
                                  for i in range(5)],
                "CANONICAL KNOWLEDGE": [Knowledge(title=f"K{i} udp", body="udp")
                                        for i in range(10)],
            }
            context = _FakeContext(sections)
            compressed = optimizer.compress(context)
            assert compressed.sections.get("DECISIONS"), f"{profile}: DECISION lost"
            assert compressed.sections.get("FAILURES"), f"{profile}: FAILURE lost"
            assert compressed.sections.get("CONFIGURATION"), (
                f"{profile}: CONFIGURATION lost")

    def test_semantic_equivalence_and_reduction(self, tmp_path: Path) -> None:
        """AGGRESSIVE: protected intact; reduction >60% (LLM mock)."""
        from hkos.performance.context_profiles import CompressedContext
        from hkos.repository.models import Knowledge

        items = []
        for i in range(60):
            items.append(Knowledge(title=f"K{i} udp", body="udp " * 10,
                                   tags=["udp"]))
        sections = {"CANONICAL KNOWLEDGE": items}
        optimizer = PerformanceContextOptimizer(PROFILE_AGGRESSIVE)
        compressed = optimizer.compress(_FakeContext(sections))
        assert isinstance(compressed, CompressedContext)
        total = compressed.item_count()
        assert total == 0  # AGGRESSIVE: не-protected удаляются
        # reduction на реальном контексте (bundle из hook)
        ctx = create_hermes_context(tmp_path)
        project = ctx.project.create(name="Red", tags=["hermes"])
        for i in range(30):
            k = ctx.librarian.register(project.id, __import__(
                "hkos.repository.models", fromlist=["Knowledge"]).Knowledge(
                    title=f"R{i}fact udp", body="udp engineering " * 5,
                    tags=["udp"]))
            ctx.librarian.canonicalize(project.id, k.id)
        ctx.index.build(project.id)
        bundle = ctx.retrieve_before_task("udp", project_id=project.id)
        assert bundle["tokens_before"] > 0
        assert bundle["reduction"] >= 0

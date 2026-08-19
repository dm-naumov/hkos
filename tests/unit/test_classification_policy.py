"""Post-Audit Refinement tests: classification policy, idempotency, validation.

Замечания аудитов v3.0/v4.0/v5.0:
- единая политика классификации (Context и Snapshot — одна логическая категория);
- литералы категорий -> CATEGORY_*;
- замкнутый словарь категорий;
- идемпотентность canonicalize/merge;
- владение SnapshotDocument (kernel).
"""

from hkos.services.classification_policy import (
    CATEGORY_ARCHITECTURE,
    CATEGORY_ARTIFACT,
    CATEGORY_CANONICAL,
    CATEGORY_CONFIGURATION,
    CATEGORY_DECISION,
    CATEGORY_FAILURE,
    CATEGORY_LIMITATION,
    CATEGORY_QUESTION,
    classify,
    is_valid_category,
    validate_category,
)
from hkos.services.librarian.knowledge_classifier import (
    CATEGORY_CONFIGURATION as C_CONFIG,
)
from hkos.services.librarian.knowledge_classifier import (
    CATEGORY_DECISION as C_DECISION,
)
from hkos.services.librarian.knowledge_classifier import (
    CATEGORY_FACT,
    CATEGORY_PATTERN,
    CATEGORY_RULE,
    VALID_CATEGORIES,
)
from hkos.services.librarian.knowledge_classifier import (
    CATEGORY_FAILURE as C_FAILURE,
)


class TestClassificationPolicy:
    """Единая логическая категория для всех потребителей."""

    def test_artifact(self) -> None:
        assert classify("artifact", "", "", "") == CATEGORY_ARTIFACT

    def test_decision_type(self) -> None:
        assert classify("decision", "", "", "") == CATEGORY_DECISION

    def test_canonical_status_priority(self) -> None:
        # CANONICAL-статус важнее категории (канонический FAILURE -> CANONICAL)
        assert classify("knowledge", C_FAILURE, "", "CANONICAL") == CATEGORY_CANONICAL

    def test_decision_category(self) -> None:
        assert classify("knowledge", C_DECISION, "", "NEW") == CATEGORY_DECISION

    def test_failure_category(self) -> None:
        assert classify("knowledge", C_FAILURE, "", "NEW") == CATEGORY_FAILURE

    def test_negative_kind(self) -> None:
        # kind=negative -> FAILURE (ранее расхождение Context/Snapshot)
        assert classify("knowledge", "", "negative", "NEW") == CATEGORY_FAILURE

    def test_rule_pattern_configuration(self) -> None:
        # RULE/PATTERN -> CONFIGURATION (ранее расхождение Context/Snapshot)
        assert classify("knowledge", CATEGORY_RULE, "", "NEW") == CATEGORY_CONFIGURATION
        assert classify("knowledge", CATEGORY_PATTERN, "", "NEW") == CATEGORY_CONFIGURATION
        assert classify("knowledge", C_CONFIG, "", "NEW") == CATEGORY_CONFIGURATION

    def test_superseded_limitation(self) -> None:
        assert classify("knowledge", CATEGORY_FACT, "", "SUPERSEDED") == CATEGORY_LIMITATION

    def test_verified_architecture(self) -> None:
        # VERIFIED -> ARCHITECTURE (ранее расхождение Context/Snapshot)
        assert classify("knowledge", CATEGORY_FACT, "", "VERIFIED") == CATEGORY_ARCHITECTURE

    def test_fact_canonical(self) -> None:
        # FACT (дефолт классификатора) -> CANONICAL
        assert classify("knowledge", CATEGORY_FACT, "", "NEW") == CATEGORY_CANONICAL

    def test_question_fallback(self) -> None:
        assert classify("knowledge", "HYPOTHESIS", "", "NEW") == CATEGORY_QUESTION
        assert classify("knowledge", "", "", "") == CATEGORY_QUESTION

    def test_closed_vocabulary(self) -> None:
        assert is_valid_category(CATEGORY_FACT) is True
        assert is_valid_category("BOGUS") is False
        assert len(VALID_CATEGORIES) == 10

    def test_validate_category(self) -> None:
        validate_category(CATEGORY_FACT)  # не бросает
        try:
            validate_category("BOGUS")
            assert False, "должно бросить ValueError"
        except ValueError:
            pass


class TestClassificationConsistency:
    """Одно Knowledge -> одна логическая категория в Context и Snapshot."""

    @staticmethod
    def _context_section(entity_type: str, category: str, kind: str, status: str) -> str:
        """Секция ContextSerializer для знания (по его собственному маппингу)."""
        from hkos.context.context_serializer import ContextSerializer
        from hkos.context.models import ContextDocument, ContextItem
        from hkos.repository.models import Knowledge

        item = ContextItem(
            entity=Knowledge(id="k1", title="T", category=category, kind=kind, status=status),
            entity_type=entity_type,
        )
        sections = ContextSerializer().sectionize(
            ContextDocument(task="t", project_id="p1", items=[item])
        )
        return next(name for name, items in sections.items() if items)

    @staticmethod
    def _snapshot_logical(entity_type: str, category: str, kind: str, status: str) -> str:
        """Логическая категория SnapshotBuilder (секции 1:1 с логическими)."""
        from hkos.index.query_contract import EntityRecord
        from hkos.snapshot.snapshot_builder import SnapshotBuilder

        sections = SnapshotBuilder._classify([
            EntityRecord(id="k1", project="p1", type=entity_type, title="T",
                         status=status, category=category, tags=[]),
        ])
        section = next(name for name, items in sections.items() if items)
        mapping = {
            "Canonical Knowledge": CATEGORY_CANONICAL,
            "Architecture": CATEGORY_ARCHITECTURE,
            "Accepted Decisions": CATEGORY_DECISION,
            "Configurations": CATEGORY_CONFIGURATION,
            "Known Failures": CATEGORY_FAILURE,
            "Known Limitations": CATEGORY_LIMITATION,
            "Artifacts": CATEGORY_ARTIFACT,
            "Open Questions": CATEGORY_QUESTION,
        }
        return mapping.get(section, CATEGORY_QUESTION)

    def test_consistency_cases(self) -> None:
        """Политика — единый источник: snapshot-секции 1:1 с classify();
        context-секции — по его собственному отображению логической категории.

        Логическая категория (classify) ОДИНАКОВА для обоих потребителей;
        маппинг на секции у потребителей свой (у Context нет секции
        Architecture/Limitations — они отображаются в ближайшие).
        """
        # (entity_type, category, kind, status, ожидаемая_логическая, ожидаемая_секция_context)
        cases = [
            ("knowledge", C_FAILURE, "negative", "NEW", CATEGORY_FAILURE, "FAILURES"),
            ("knowledge", CATEGORY_RULE, "", "NEW", CATEGORY_CONFIGURATION, "CONFIGURATION"),
            ("knowledge", CATEGORY_PATTERN, "", "NEW", CATEGORY_CONFIGURATION, "CONFIGURATION"),
            ("knowledge", C_DECISION, "", "NEW", CATEGORY_DECISION, "DECISIONS"),
            ("knowledge", CATEGORY_FACT, "", "VERIFIED",
             CATEGORY_ARCHITECTURE, "CANONICAL KNOWLEDGE"),
            ("knowledge", CATEGORY_FACT, "", "NEW",
             CATEGORY_CANONICAL, "CANONICAL KNOWLEDGE"),
            ("knowledge", CATEGORY_FACT, "", "CANONICAL",
             CATEGORY_CANONICAL, "CANONICAL KNOWLEDGE"),
            ("knowledge", CATEGORY_FACT, "", "SUPERSEDED", CATEGORY_LIMITATION, "OPEN QUESTIONS"),
            ("decision", "", "", "NEW", CATEGORY_DECISION, "DECISIONS"),
            ("artifact", "", "", "NEW", CATEGORY_ARTIFACT, "ARTIFACTS"),
            ("knowledge", "HYPOTHESIS", "", "NEW", CATEGORY_QUESTION, "OPEN QUESTIONS"),
        ]
        for entity_type, category, kind, status, logical, context_section in cases:
            # Политика (единый источник)
            assert classify(entity_type, category, kind, status) == logical
            # Snapshot: секции 1:1 с логической категорией
            assert self._snapshot_logical(entity_type, category, kind, status) == logical
            # Context: секция по его маппингу
            assert self._context_section(entity_type, category, kind, status) == context_section

    def test_negative_kind_unified_via_category(self) -> None:
        """kind=negative в реальном пайплайне несёт категорию FAILURE
        (классификатор присваивает при регистрации) — унифицировано.
        """
        assert classify("knowledge", C_FAILURE, "negative", "NEW") == CATEGORY_FAILURE
        assert self._snapshot_logical("knowledge", C_FAILURE, "negative", "NEW") == CATEGORY_FAILURE
        assert self._context_section("knowledge", C_FAILURE, "negative", "NEW") == "FAILURES"

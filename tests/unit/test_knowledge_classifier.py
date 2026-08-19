"""Unit tests for KnowledgeClassifier (DS-006 §8)."""

from hkos.repository.models import Knowledge
from hkos.services.librarian.knowledge_classifier import (
    CATEGORY_CONFIGURATION,
    CATEGORY_DECISION,
    CATEGORY_FACT,
    CATEGORY_FAILURE,
    CATEGORY_HYPOTHESIS,
    CATEGORY_SUCCESS,
    VALID_CATEGORIES,
    KnowledgeClassifier,
)


class TestKnowledgeClassifier:
    """Test suite for deterministic classification."""

    def test_default_is_fact(self) -> None:
        assert KnowledgeClassifier.classify(
            Knowledge(title="Something plain", body="text")
        ) == CATEGORY_FACT

    def test_negative_kind_is_failure(self) -> None:
        assert KnowledgeClassifier.classify(
            Knowledge(title="X", kind="negative")
        ) == CATEGORY_FAILURE

    def test_failure_marker(self) -> None:
        assert KnowledgeClassifier.classify(
            Knowledge(title="TUN ломает DNS", body="")
        ) == CATEGORY_FAILURE

    def test_success_marker(self) -> None:
        assert KnowledgeClassifier.classify(
            Knowledge(title="TProxy работает", body="")
        ) == CATEGORY_SUCCESS

    def test_hypothesis_marker(self) -> None:
        assert KnowledgeClassifier.classify(
            Knowledge(title="Гипотеза: причина в MTU", body="")
        ) == CATEGORY_HYPOTHESIS

    def test_decision_marker(self) -> None:
        assert KnowledgeClassifier.classify(
            Knowledge(title="Решение: использовать TProxy", body="")
        ) == CATEGORY_DECISION

    def test_configuration_marker(self) -> None:
        assert KnowledgeClassifier.classify(
            Knowledge(title="Конфигурация sing-box", body="")
        ) == CATEGORY_CONFIGURATION

    def test_case_insensitive(self) -> None:
        assert KnowledgeClassifier.classify(
            Knowledge(title="FAILED after update", body="")
        ) == CATEGORY_FAILURE

    def test_valid_categories(self) -> None:
        assert len(VALID_CATEGORIES) == 10
        assert KnowledgeClassifier.is_valid(CATEGORY_FACT)
        assert not KnowledgeClassifier.is_valid("BOGUS")

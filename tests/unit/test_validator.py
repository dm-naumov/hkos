"""Unit tests for ContextValidator (DS-009 §16)."""

from hkos.context.context_serializer import ContextSerializer
from hkos.context.context_validator import ContextValidator
from hkos.context.models import ContextDocument, ContextItem
from hkos.context.snapshot_loader import SnapshotDocument
from hkos.repository.models import Knowledge

SECTIONS = ["TASK", "PROJECT", "CURRENT STATE", "CANONICAL KNOWLEDGE",
            "DECISIONS", "FAILURES", "ARTIFACTS", "CONFIGURATION",
            "OPEN QUESTIONS"]


class TestContextValidator:
    """Валидация: дубликаты, UUID, Snapshot, обязательные секции, порядок."""

    def _validator(self) -> ContextValidator:
        return ContextValidator(ContextSerializer(SECTIONS))

    def test_valid_context(self) -> None:
        context = ContextDocument(
            task="udp",
            project_id="11111111-2222-3333-4444-555555555555",
            items=[
                ContextItem(
                    entity=Knowledge(id="aaaaaaaa-1111-2222-3333-444455556666"),
                    entity_type="knowledge",
                )
            ],
        )
        result = self._validator().validate(context)
        assert result.valid is True

    def test_duplicates_detected(self) -> None:
        context = ContextDocument(
            task="t", project_id="p1",
            items=[
                ContextItem(entity=Knowledge(id="k1"), entity_type="knowledge"),
                ContextItem(entity=Knowledge(id="k1"), entity_type="knowledge"),
            ],
        )
        result = self._validator().validate(context)
        assert result.valid is False
        assert any("Duplicate" in e for e in result.errors)

    def test_empty_task(self) -> None:
        context = ContextDocument(project_id="p1")
        result = self._validator().validate(context)
        assert result.valid is False
        assert any("TASK" in e for e in result.errors)

    def test_snapshot_project_mismatch(self) -> None:
        context = ContextDocument(
            task="t", project_id="p1",
            snapshot=SnapshotDocument(snapshot_id="s1", project_id="OTHER"),
        )
        result = self._validator().validate(context)
        assert result.valid is False
        assert any("project mismatch" in e for e in result.errors)

    def test_snapshot_without_id(self) -> None:
        context = ContextDocument(
            task="t", project_id="p1",
            snapshot=SnapshotDocument(project_id="p1"),
        )
        result = self._validator().validate(context)
        assert result.valid is False
        assert any("snapshot_id" in e for e in result.errors)

    def test_non_uuid_warns(self) -> None:
        context = ContextDocument(
            task="t", project_id="p1",
            items=[ContextItem(entity=Knowledge(id="not-a-uuid"), entity_type="knowledge")],
        )
        result = self._validator().validate(context)
        assert any("Non-UUID" in w for w in result.warnings)

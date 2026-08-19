"""Unit tests for ContextSerializer (DS-009 §14)."""

from typing import Any

from hkos.context.context_serializer import ContextSerializer
from hkos.context.models import ContextDocument, ContextItem
from hkos.repository.models import Knowledge

SECTIONS = ["TASK", "PROJECT", "CURRENT STATE", "CANONICAL KNOWLEDGE",
            "DECISIONS", "FAILURES", "ARTIFACTS", "CONFIGURATION",
            "OPEN QUESTIONS"]


def _item(
    entity: Knowledge,
    entity_type: str = "knowledge",
    **kw: Any,
) -> ContextItem:
    return ContextItem(entity=entity, entity_type=entity_type, **kw)


class TestContextSerializer:
    """Стабильная сериализация (фиксированный порядок секций)."""


    def _serializer(self) -> ContextSerializer:
        return ContextSerializer(SECTIONS)

    def _context(self) -> ContextDocument:
        return ContextDocument(
            task="udp routing",
            project_id="p1",
            items=[
                _item(Knowledge(id="k1", title="UDP fix", status="CANONICAL", category="FACT")),
                _item(Knowledge(id="k2", title="TUN fail", kind="negative", category="FAILURE")),
                _item(Knowledge(id="k3", title="Config", category="CONFIGURATION")),
            ],
        )

    def test_fixed_section_order(self) -> None:
        text = self._serializer().serialize(self._context())
        positions = [text.find(f"## {s}") for s in SECTIONS]
        assert all(p >= 0 for p in positions)
        assert positions == sorted(positions)

    def test_canonical_section(self) -> None:
        text = self._serializer().serialize(self._context())
        assert "UDP fix" in text
        assert "CANONICAL KNOWLEDGE" in text

    def test_failures_section(self) -> None:
        text = self._serializer().serialize(self._context())
        assert "TUN fail" in text
        assert "FAILURES" in text

    def test_configuration_section(self) -> None:
        text = self._serializer().serialize(self._context())
        assert "Config" in text
        assert "CONFIGURATION" in text

    def test_stable_output(self) -> None:
        context = self._context()
        first = self._serializer().serialize(context)
        second = self._serializer().serialize(context)
        assert first == second

    def test_sectionize_all_sections_present(self) -> None:
        sections = self._serializer().sectionize(self._context())
        assert set(sections.keys()) == set(SECTIONS)

    def test_empty_sections_use_dash(self) -> None:
        text = self._serializer().serialize(ContextDocument(task="t", project_id="p"))
        assert "-" in text

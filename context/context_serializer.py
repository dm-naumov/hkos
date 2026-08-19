"""HKOS Context Serializer (DS-009 §14, IP-009)
=============================================
Стабильная сериализация контекста в секции.

Порядок секций ФИКСИРОВАН (из конфигурации context.serializer.sections):
TASK, PROJECT, CURRENT STATE, CANONICAL KNOWLEDGE, DECISIONS,
FAILURES, ARTIFACTS, CONFIGURATION, OPEN QUESTIONS.
"""

from hkos.context.models import ContextDocument, ContextItem
from hkos.services.classification_policy import (
    CATEGORY_ARCHITECTURE,
    CATEGORY_ARTIFACT,
    CATEGORY_CANONICAL,
    CATEGORY_CONFIGURATION,
    CATEGORY_DECISION,
    CATEGORY_FAILURE,
    CATEGORY_LIMITATION,
    classify,
)

__all__ = ["ContextSerializer"]

# Типы/категории -> секции.
_SECTION_TASK: str = "TASK"
_SECTION_PROJECT: str = "PROJECT"
_SECTION_CURRENT_STATE: str = "CURRENT STATE"
_SECTION_CANONICAL: str = "CANONICAL KNOWLEDGE"
_SECTION_DECISIONS: str = "DECISIONS"
_SECTION_FAILURES: str = "FAILURES"
_SECTION_ARTIFACTS: str = "ARTIFACTS"
_SECTION_CONFIGURATION: str = "CONFIGURATION"
_SECTION_OPEN_QUESTIONS: str = "OPEN QUESTIONS"

_DEFAULT_SECTIONS: tuple[str, ...] = (
    _SECTION_TASK,
    _SECTION_PROJECT,
    _SECTION_CURRENT_STATE,
    _SECTION_CANONICAL,
    _SECTION_DECISIONS,
    _SECTION_FAILURES,
    _SECTION_ARTIFACTS,
    _SECTION_CONFIGURATION,
    _SECTION_OPEN_QUESTIONS,
)


class ContextSerializer:
    """Сериализация контекста (стабильный порядок секций)."""

    def __init__(
        self,
        sections: list[str] | None = None,
        body_limit: int = 200,
    ) -> None:
        """Инициализация сериализатора.

        Args:
            sections: Порядок секций (из конфигурации); по умолчанию
                фиксированный набор DS-009.
            body_limit: Ограничение длины body в сериализации
                (context.serializer.body_limit; по умолчанию 200 —
                Audit Remediation DS-009A, поведение не изменено).

        """
        self._sections: tuple[str, ...] = (
            tuple(sections) if sections else _DEFAULT_SECTIONS
        )
        self._body_limit = max(0, body_limit)

    @property
    def sections(self) -> tuple[str, ...]:
        """Порядок секций."""
        return self._sections

    @staticmethod
    def _item_section(item: ContextItem) -> str:
        """Секция для элемента: единая политика классификации (classification_policy).

        Логическая категория определяется ЕДИНЫМ модулем (одно Knowledge —
        одна категория независимо от потребителя); здесь — только
        отображение логической категории на секции Context.
        """
        category = classify(
            entity_type=item.entity_type,
            category=getattr(item.entity, "category", "") or "",
            kind=getattr(item.entity, "kind", "") or "",
            status=getattr(item.entity, "status", "") or "",
        )
        if category == CATEGORY_ARTIFACT:
            return _SECTION_ARTIFACTS
        if category == CATEGORY_DECISION:
            return _SECTION_DECISIONS
        if category == CATEGORY_FAILURE:
            return _SECTION_FAILURES
        if category == CATEGORY_CONFIGURATION:
            return _SECTION_CONFIGURATION
        if category in (CATEGORY_CANONICAL, CATEGORY_ARCHITECTURE):
            return _SECTION_CANONICAL
        if category == CATEGORY_LIMITATION:
            return _SECTION_OPEN_QUESTIONS
        return _SECTION_OPEN_QUESTIONS  # CATEGORY_QUESTION

    def sectionize(
        self, context: ContextDocument
    ) -> dict[str, list[ContextItem]]:
        """Разложить элементы по секциям (фиксированный порядок)."""
        sections: dict[str, list[ContextItem]] = {
            name: [] for name in self._sections
        }
        for item in context.items:
            section = self._item_section(item)
            if section not in sections:
                section = _SECTION_OPEN_QUESTIONS
            sections[section].append(item)
        return sections

    def serialize(self, context: ContextDocument) -> str:
        """Сериализовать контекст в текст (стабильный порядок секций)."""
        sections = self.sectionize(context)
        lines: list[str] = []
        for name in self._sections:
            lines.append(f"## {name}")
            if name == _SECTION_TASK:
                lines.append(context.task if context.task else "-")
            elif name == _SECTION_PROJECT:
                lines.append(context.project_id if context.project_id else "-")
            elif name == _SECTION_CURRENT_STATE:
                if context.snapshot is not None:
                    lines.append(
                        f"snapshot={context.snapshot.snapshot_id} "
                        f"({context.snapshot.timestamp})"
                    )
                else:
                    lines.append("-")
            else:
                items = sections.get(name, [])
                if not items:
                    lines.append("-")
                for item in items:
                    title = (
                        getattr(item.entity, "title", "")
                        or getattr(item.entity, "name", "")
                        or getattr(item.entity, "id", "")
                    )
                    body = getattr(item.entity, "body", "") or ""
                    line = f"- {title}"
                    if body:
                        if self._body_limit > 0:
                            body = body[: self._body_limit]
                        line += f": {body}"
                    lines.append(line)
            lines.append("")
        return "\n".join(lines)

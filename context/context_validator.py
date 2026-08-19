"""HKOS Context Validator (DS-009 §16, IP-009)
=============================================
Validator проверяет:
- отсутствие дубликатов (по id);
- отсутствие битых UUID;
- корректность Snapshot (id непустой, project совпадает);
- отсутствие пустых обязательных секций (TASK, PROJECT);
- корректность порядка секций.
"""

import re

from hkos.context.context_serializer import ContextSerializer
from hkos.context.models import ContextDocument
from hkos.index.validation import ValidationResult

__all__ = ["ContextValidator"]

_UUID = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


class ContextValidator:
    """Валидация документа контекста (только чтение)."""

    def __init__(self, serializer: ContextSerializer) -> None:
        """Инициализация валидатора.

        Args:
            serializer: Сериализатор (порядок секций).

        """
        self._serializer = serializer

    def validate(self, context: ContextDocument) -> ValidationResult:
        """Проверить документ контекста.

        Args:
            context: Документ контекста.

        Returns:
            ValidationResult.

        """
        errors: list[str] = []
        warnings: list[str] = []

        # 1. Дубликаты
        ids = [
            getattr(item.entity, "id", "") for item in context.items
        ]
        duplicates = {i for i in ids if i and ids.count(i) > 1}
        if duplicates:
            errors.append(f"Duplicate items in context: {sorted(duplicates)}")

        # 2. Битые UUID
        for item in context.items:
            entity_id = getattr(item.entity, "id", "")
            if entity_id and not _UUID.match(entity_id):
                warnings.append(f"Non-UUID id in context: {entity_id!r}")

        # 3. Snapshot корректность
        if context.snapshot is not None:
            if not context.snapshot.snapshot_id:
                errors.append("Snapshot present but snapshot_id is empty")
            if (
                context.snapshot.project_id
                and context.snapshot.project_id != context.project_id
            ):
                errors.append(
                    "Snapshot project mismatch: "
                    f"{context.snapshot.project_id} != {context.project_id}"
                )

        # 4. Пустые обязательные секции
        if not context.task:
            errors.append("Empty mandatory section: TASK")
        if not context.project_id:
            errors.append("Empty mandatory section: PROJECT")

        # 5. Порядок секций
        sections = self._serializer.sectionize(context)
        expected = list(self._serializer.sections)
        actual = [name for name in expected if sections.get(name)]
        if actual != expected and set(actual) != set(expected):
            warnings.append("Section order does not match fixed sequence")

        return ValidationResult(valid=not errors, errors=errors, warnings=warnings)

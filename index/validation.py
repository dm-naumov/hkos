"""HKOS Index Validation Result (DS-007 §12)
============================================
ValidationResult для Index Layer.

Сознательное решение: НЕ импортируем ValidationResult из services
(это нарушило бы Dependency Rule — index ниже services; при будущей
интеграции Librarian -> IndexEngine возник бы цикл). Небольшое
дублирование dataclass'а зафиксировано как осознанное; консолидация
в общий kernel-модуль — при появлении такового.
"""

__all__ = ["ValidationResult"]


class ValidationResult:
    """Результат валидации (валидность + ошибки + предупреждения)."""

    def __init__(
        self,
        valid: bool,
        errors: list[str] | None = None,
        warnings: list[str] | None = None,
    ) -> None:
        """Инициализация результата.

        Args:
            valid: Прошла ли проверка.
            errors: Критические проблемы.
            warnings: Некритические замечания.

        """
        self.valid = valid
        self.errors: list[str] = list(errors) if errors else []
        self.warnings: list[str] = list(warnings) if warnings else []

    def __bool__(self) -> bool:
        """Валидно."""
        return self.valid

    def as_dict(self) -> dict[str, object]:
        """Результат как словарь."""
        return {
            "valid": self.valid,
            "errors": self.errors,
            "warnings": self.warnings,
        }

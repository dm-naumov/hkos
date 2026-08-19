"""HKOS Migration Executor (DS-011 Rev.1.2 §8/§14, IP-011 ЭТАП 5)
================================================================
Применение шага миграции. ОТВЕТСТВЕННОСТЬ ТОЛЬКО за применение:
- НИКАКИХ backup; НИКАКИХ rollback; НИКАКИХ rebuild; НИКАКИХ
  validate; НИКАКИХ журналов (нет оркестрации).

Идемпотентность: повторный apply() уже выполненного шага допускается
и завершается корректно (шаги идемпотентны по DS-011 §8/§14; executor
не хранит состояния и повторно вызывает применение).

Механизм применения: step.apply(), если шаг его предоставляет
(duck-typed), иначе — обработчик, зарегистрированный для
migration_id (dependency injection; MigrationStep из Registry —
frozen dataclass без apply).
"""

from collections.abc import Mapping
from typing import Callable

from hkos.migration.exceptions import MigrationError
from hkos.migration.migration_registry import MigrationStep

__all__ = ["MigrationExecutor"]


class MigrationExecutor:
    """Исполнитель шагов миграции (идемпотентный)."""

    def __init__(
        self,
        appliers: Mapping[str, Callable[[MigrationStep], None]] | None = None,
    ) -> None:
        """Инициализация исполнителя.

        Args:
            appliers: Обработчики применения по migration_id
                (dependency injection; шаг Registry не несёт логики).

        """
        self._appliers: dict[str, Callable[[MigrationStep], None]] = {
            **(appliers or {}),
        }

    def apply(self, step: MigrationStep) -> None:
        """Применить шаг (идемпотентно; повторный apply = повторный
        вызов применения — корректно для идемпотентных шагов).

        Args:
            step: Шаг миграции.

        Raises:
            MigrationError: обработчик отсутствует; применение упало.

        """
        apply_fn = getattr(step, "apply", None)
        if callable(apply_fn):
            try:
                apply_fn()
            except Exception as exc:
                raise MigrationError(
                    f"Migration step failed: {step.migration_id}: {exc}"
                ) from exc
            return
        handler = self._appliers.get(step.migration_id)
        if handler is None:
            raise MigrationError(
                f"No applier registered for migration {step.migration_id!r}"
            )
        try:
            handler(step)
        except Exception as exc:
            raise MigrationError(
                f"Migration step failed: {step.migration_id}: {exc}"
            ) from exc

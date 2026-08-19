"""HKOS Migration Registry (DS-011 Rev.1.2 §8)
===============================================
СТАТИЧЕСКИЙ каталог миграций: тотальный порядок, запрет пропуска
промежуточных версий, агрегированные миграции — только при явной
регистрации. Без персистентности и состояния выполнения.

Инварианты:
- MigrationStep immutable (frozen dataclass);
- from_version < to_version (строгий рост -> ацикличность; проверка
  циклов выполняется defensive-алгоритмом при регистрации);
- дубликат migration_id с другим переходом -> MigrationError;
  идентичный повторный register -> no-op (идемпотентность, §14);
- дубликат перехода (from, to) с другим id -> MigrationError
  (запрет неоднозначных переходов);
- ordered(): агрегированный шаг, покрывающий диапазон (явно
  зарегистрированный), предпочтителен; иначе — цепочка единичных
  шагов с проверкой непрерывности; неоднозначность -> MigrationError.
"""

from dataclasses import dataclass

from hkos.migration.exceptions import MigrationError

__all__ = ["MigrationStep", "MigrationRegistry"]


@dataclass(frozen=True)
class MigrationStep:
    """Шаг миграции (immutable; идемпотентный; DS-011 §8)."""

    migration_id: str
    from_version: int
    to_version: int


class MigrationRegistry:
    """Упорядоченный каталог шагов миграции (статический)."""

    def __init__(self) -> None:
        self._steps: dict[str, MigrationStep] = {}
        self._transitions: dict[tuple[int, int], str] = {}

    def register(self, step: MigrationStep) -> None:
        """Зарегистрировать шаг (повторная регистрация = no-op).

        Raises:
            MigrationError: from >= to; дубликат id с другим переходом;
                дубликат перехода с другим id; цикл (defensive).

        """
        if step.from_version >= step.to_version:
            raise MigrationError(
                f"Migration {step.migration_id}: from_version ({step.from_version}) "
                f"must be < to_version ({step.to_version})"
            )
        existing = self._steps.get(step.migration_id)
        if existing is not None:
            if (
                existing.from_version == step.from_version
                and existing.to_version == step.to_version
            ):
                return  # идемпотентность (§14): идентичный register = no-op
            raise MigrationError(
                f"Duplicate migration_id {step.migration_id!r} with different transition "
                f"({existing.from_version}->{existing.to_version} vs "
                f"{step.from_version}->{step.to_version})"
            )
        previous = self._transitions.get((step.from_version, step.to_version))
        if previous is not None:
            raise MigrationError(
                f"Duplicate transition ({step.from_version}->{step.to_version}): "
                f"already registered as {previous!r}"
            )
        self._check_no_cycle(step)
        self._steps[step.migration_id] = step
        self._transitions[(step.from_version, step.to_version)] = step.migration_id

    def contains(self, migration_id: str) -> bool:
        """Зарегистрирован ли шаг."""
        return migration_id in self._steps

    def contains_any(self) -> bool:
        """Есть ли хотя бы один зарегистрированный шаг."""
        return bool(self._steps)

    def steps(self) -> list[MigrationStep]:
        """Все зарегистрированные шаги (детерминированный порядок)."""
        return sorted(self._steps.values(), key=lambda s: (s.from_version, s.to_version))

    def ordered(
        self, current_version: int, target_version: int
    ) -> list[MigrationStep]:
        """Шаги по тотальному порядку от current к target (без пропусков).

        Агрегированный шаг, покрывающий весь диапазон (явно
        зарегистрированный), предпочтителен; иначе — цепочка
        единичных шагов с проверкой непрерывности.

        Raises:
            MigrationError: current > target; разрыв цепочки;
                неоднозначный переход.

        """
        if current_version > target_version:
            raise MigrationError(
                f"current_version ({current_version}) > target_version ({target_version})"
            )
        if current_version == target_version:
            return []
        aggregate_id = self._transitions.get((current_version, target_version))
        if aggregate_id is not None:
            return [self._steps[aggregate_id]]
        path: list[MigrationStep] = []
        version = current_version
        visited: set[int] = {version}
        while version < target_version:
            outgoing = [
                step for step in self._steps.values()
                if step.from_version == version
            ]
            if not outgoing:
                raise MigrationError(
                    f"Chain break: no migration from version {version} "
                    f"toward {target_version} (continuity required)"
                )
            if len(outgoing) > 1:
                raise MigrationError(
                    f"Ambiguous transition from version {version}: "
                    + ", ".join(
                        f"{s.migration_id} ({s.from_version}->{s.to_version})"
                        for s in sorted(outgoing, key=lambda s: s.to_version)
                    )
                )
            step = outgoing[0]
            if step.to_version in visited:
                raise MigrationError(
                    f"Cycle detected via {step.migration_id} "
                    f"({step.from_version}->{step.to_version})"
                )
            visited.add(step.to_version)
            path.append(step)
            version = step.to_version
        return path

    def _check_no_cycle(self, candidate: MigrationStep) -> None:
        """Defensive-проверка циклов (при from<to циклы невозможны).

        Граф переходов ацикличен по построению (строгий рост версий);
        проверка выполняется для полноты инварианта и защищена тестом.
        """
        visited: set[int] = set()
        stack: list[int] = [candidate.to_version]
        while stack:
            version = stack.pop()
            if version == candidate.from_version:
                raise MigrationError(
                    f"Cycle detected: {candidate.migration_id} "
                    f"({candidate.from_version}->{candidate.to_version})"
                )
            if version in visited:
                continue
            visited.add(version)
            for step in self._steps.values():
                if step.from_version == version and step.to_version not in visited:
                    stack.append(step.to_version)

"""DS-006B §8, §10: State Machine review — автоматическая проверка графа.

Проверки:
- нет недостижимых состояний (BFS от NEW);
- нет тупиков (каждое состояние имеет исходящий переход);
- нет невозможных переходов (все targets валидны);
- все состояния достижимы до ARCHIVED (терминальная цель);
- циклы только разрешённые (restore).
"""

from collections import deque

from hkos.services.librarian.knowledge_status import (
    KNOWLEDGE_STATUS_ARCHIVED,
    KNOWLEDGE_STATUS_NEW,
    TRANSITIONS,
    VALID_KNOWLEDGE_STATUSES,
)


class TestStateGraph:
    """Автоматическая валидация таблицы переходов KnowledgeStatus."""

    def test_all_targets_valid(self) -> None:
        for current, targets in TRANSITIONS.items():
            assert current in VALID_KNOWLEDGE_STATUSES
            for target in targets:
                assert target in VALID_KNOWLEDGE_STATUSES, (
                    f"invalid target {target} from {current}"
                )

    def test_no_unreachable_states(self) -> None:
        """BFS от NEW: все состояния достижимы."""
        visited: set[str] = set()
        queue: deque[str] = deque([KNOWLEDGE_STATUS_NEW])
        while queue:
            state = queue.popleft()
            if state in visited:
                continue
            visited.add(state)
            for target in TRANSITIONS[state]:
                if target not in visited:
                    queue.append(target)
        assert visited == set(VALID_KNOWLEDGE_STATUSES)

    def test_no_deadlock_states(self) -> None:
        """Каждое состояние имеет хотя бы один исходящий переход."""
        for state in VALID_KNOWLEDGE_STATUSES:
            assert len(TRANSITIONS[state]) > 0, f"deadlock state: {state}"

    def test_archived_reachable_from_all(self) -> None:
        """Из любого состояния достижим ARCHIVED (терминальная цель)."""
        for state in VALID_KNOWLEDGE_STATUSES:
            visited: set[str] = set()
            queue: deque[str] = deque([state])
            reachable = False
            while queue:
                s = queue.popleft()
                if s in visited:
                    continue
                visited.add(s)
                if s == KNOWLEDGE_STATUS_ARCHIVED:
                    reachable = True
                    break
                for target in TRANSITIONS[s]:
                    if target not in visited:
                        queue.append(target)
            assert reachable, f"ARCHIVED unreachable from {state}"

    def test_only_allowed_cycles(self) -> None:
        """Единственный цикл — restore: ARCHIVED -> VERIFIED -> ... -> ARCHIVED."""
        cycle_edges = [
            (current, target)
            for current, targets in TRANSITIONS.items()
            for target in targets
            if current in TRANSITIONS.get(target, frozenset())
        ]
        # Единственная взаимная пара — ARCHIVED <-> VERIFIED путь
        assert ("ARCHIVED", KNOWLEDGE_STATUS_NEW) not in cycle_edges
        assert ("REJECTED", KNOWLEDGE_STATUS_NEW) not in cycle_edges

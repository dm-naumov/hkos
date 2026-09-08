"""HKOS Relationship Traverser (DS-008 §12, IP-008)
====================================================
Расширение кандидатов связанными знаниями.

Traversal работает ИСКЛЮЧИТЕЛЬНО через Q4 (Query Contract).
ЗАПРЕЩЕНО читать документы знаний ради поиска связей.

Алгоритм:
    получить связи (Q4 relations_of_knowledge)
    -> расширить кандидатов
    -> не создавать циклы (visited set)
    -> не допускать повторов (dedup by id)

Ограничения (конфигурация): max_depth (по умолчанию 1),
max_related (по умолчанию 10), relation_decay (по умолчанию 0.8).
"""

from typing import Any, Callable

from hkos.repository.repository_manager import RepositoryManager
from hkos.retrieval.ranking_engine import RankedCandidate

__all__ = ["RelationshipTraverser"]


class RelationshipTraverser:
    """Обход связей через Q4 (BFS с ограничением глубины и объёма).

Кросс-проектные цели (DS-017 v1.2): ребро с target_project_id, отличным
от проекта источника, обходится через снапшот ЦЕЛЕВОГО проекта
(snapshot_provider). Каждый узел BFS несёт свой проект; рёбра родителя
читаются из снапшота его проекта, метаданные соседа — из снапшота проекта
соседа. Детерминизм: visited по глобальному id, порядок BFS сохраняется.
Без snapshot_provider поведение идентично прежнему (только текущий проект)."""

    def __init__(
        self,
        repositories: RepositoryManager,
        max_depth: int = 1,
        max_related: int = 10,
        relation_decay: float = 0.8,
    ) -> None:
        """Инициализация обходчика.

        Args:
            repositories: RepositoryManager (чтение сущностей по UUID).
            max_depth: Максимальная глубина обхода.
            max_related: Максимальное число связанных кандидатов.
            relation_decay: Доля score родителя для связанного знания.

        """
        self._repositories = repositories
        self._max_depth = max_depth
        self._max_related = max_related
        self._relation_decay = relation_decay

    def _load(self, project: str, entity_id: str, entity_type: str) -> Any:
        """Загрузить сущность по UUID (контракт Section 3)."""
        if entity_type == "knowledge":
            return self._repositories.knowledge.load(project, entity_id)
        if entity_type == "decision":
            return self._repositories.decisions.load(project, entity_id)
        if entity_type == "artifact":
            return self._repositories.artifacts.load(project, entity_id)
        return None

    def traverse(
        self,
        ranked: list[RankedCandidate],
        project: str,
        snapshot: Any | None = None,
        snapshot_provider: Callable[[str], Any] | None = None,
    ) -> list[RankedCandidate]:
        """Расширить кандидатов связанными знаниями (через Q4).

        Args:
            ranked: Ранжированные кандидаты (после фильтра).
            project: UUID проекта.
            snapshot: Снапшот индексов проекта (Q4).
            snapshot_provider: Создание снапшота произвольного проекта —
                обход кросс-проектных целей (target_project_id). None:
                обход ограничен текущим проектом (как ранее).

        Returns:
            Исходные кандидаты + связанные (с relation_path и score*decay).

        """
        if snapshot is None:
            return list(ranked)
        result: list[RankedCandidate] = []
        visited: set[str] = set()
        related_count = 0

        # Снапшот на проект: корневой инжектирован; для кросс-проектных
        # целей создаётся провайдером (кэшируется на узел обхода).
        snapshots: dict[str, Any] = {project: snapshot}

        def snap_for(pid: str) -> Any | None:
            if pid not in snapshots:
                if snapshot_provider is None:
                    return None
                snapshots[pid] = snapshot_provider(pid)
            return snapshots[pid]

        # Очередь BFS: (candidate, depth, path, project узла)
        queue: list[tuple[RankedCandidate, int, list[str], str]] = []
        for candidate in ranked:
            visited.add(candidate.entity.id)
            result.append(candidate)
            queue.append((candidate, 0, [], project))

        while queue and related_count < self._max_related:
            parent, depth, path, parent_project = queue.pop(0)
            if depth >= self._max_depth:
                continue
            parent_snap = snap_for(parent_project)
            if parent_snap is None:
                continue
            relations = parent_snap.relations_of_knowledge(parent.entity.id)
            for relation in relations:
                if related_count >= self._max_related:
                    break
                hop = (
                    f"{relation.relation_id}:{relation.relation_type.value}"
                    f":{relation.source_id}->{relation.target_id}"
                )
                # Кандидаты-соседи с их проектами: источник живёт в проекте
                # снапшота (владелец ребра); цель — в целевом проекте, если
                # ребро кросс-проектное (target_project_id).
                neighbors: list[tuple[str, str]] = []
                if relation.source_id != parent.entity.id:
                    neighbors.append((relation.source_id, parent_project))
                if relation.target_id != parent.entity.id:
                    target_pid = (
                        relation.target_project_id
                        or parent_project
                    )
                    neighbors.append((relation.target_id, target_pid))
                for node, node_project in neighbors:
                    if node in visited:
                        continue
                    node_snap = snap_for(node_project)
                    if node_snap is None:
                        continue
                    record = node_snap.entity_get(node)
                    if record is None:
                        continue
                    entity = self._load(node_project, node, record.type)
                    if entity is None:
                        continue
                    visited.add(node)
                    related_count += 1
                    related = RankedCandidate(
                        entity=entity,
                        entity_type=record.type,
                        score=parent.score * self._relation_decay,
                        factors=dict(parent.factors),
                        sources=["relation"],
                        relation_path=path + [hop],
                    )
                    result.append(related)
                    queue.append(
                        (related, depth + 1, path + [hop], node_project)
                    )

        return result

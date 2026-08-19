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

from typing import Any

from hkos.repository.repository_manager import RepositoryManager
from hkos.retrieval.ranking_engine import RankedCandidate

__all__ = ["RelationshipTraverser"]


class RelationshipTraverser:
    """Обход связей через Q4 (BFS с ограничением глубины и объёма)."""

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
    ) -> list[RankedCandidate]:
        """Расширить кандидатов связанными знаниями (через Q4).

        Args:
            ranked: Ранжированные кандидаты (после фильтра).
            project: UUID проекта.

        Returns:
            Исходные кандидаты + связанные (с relation_path и score*decay).

        """
        if snapshot is None:
            return list(ranked)
        result: list[RankedCandidate] = []
        visited: set[str] = set()
        related_count = 0

        # Очередь BFS: (candidate, depth, path)
        queue: list[tuple[RankedCandidate, int, list[str]]] = [
            (candidate, 0, []) for candidate in ranked
        ]
        for candidate in ranked:
            visited.add(candidate.entity.id)
            result.append(candidate)

        while queue and related_count < self._max_related:
            parent, depth, path = queue.pop(0)
            if depth >= self._max_depth:
                continue
            relations = snapshot.relations_of_knowledge(parent.entity.id)
            for relation in relations:
                if related_count >= self._max_related:
                    break
                hop = (
                    f"{relation.relation_id}:{relation.relation_type.value}"
                    f":{relation.source_id}->{relation.target_id}"
                )
                for node in (relation.source_id, relation.target_id):
                    if node == parent.entity.id or node in visited:
                        continue
                    record = snapshot.entity_get(node)
                    if record is None:
                        continue
                    entity = self._load(project, node, record.type)
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
                    queue.append((related, depth + 1, path + [hop]))

        return result

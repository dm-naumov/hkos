"""Unit tests for ContextOptimizer (DS-009 §11)."""

from typing import Any

from hkos.context.context_optimizer import ContextOptimizer
from hkos.context.models import ContextDocument, ContextItem
from hkos.context.token_estimator import TokenEstimator
from hkos.repository.models import Knowledge


def _item(
    entity: Knowledge,
    score: float = 50.0,
    source: str = "retrieval",
    **kw: Any,
) -> ContextItem:
    return ContextItem(
        entity=entity, entity_type="knowledge", score=score, source=source, **kw
    )


class TestContextOptimizer:
    """Dedup, статус-фильтры, canonical merge, бюджет профиля."""


    def _optimizer(
        self, limits: dict[str, int] | None = None
    ) -> ContextOptimizer:
        return ContextOptimizer(
            TokenEstimator(characters_per_token=4, words_per_token=1),
            profile_limits=limits or {},
        )

    def test_dedup_by_id(self) -> None:
        opt = self._optimizer()
        context = ContextDocument(
            task="t", project_id="p1",
            items=[
                _item(Knowledge(id="k1", title="A")),
                _item(Knowledge(id="k1", title="A")),
                _item(Knowledge(id="k2", title="B")),
            ],
        )
        result = opt.optimize(context)
        assert len(result.items) == 2
        assert any(i.excluded_reason == "duplicate" for i in result.excluded)

    def test_removes_archived(self) -> None:
        opt = self._optimizer()
        context = ContextDocument(
            task="t", project_id="p1",
            items=[
                _item(Knowledge(id="k1", title="A", status="NEW")),
                _item(Knowledge(id="k2", title="B", status="ARCHIVED")),
                _item(Knowledge(id="k3", title="C", status="REJECTED")),
                _item(Knowledge(id="k4", title="D", status="SUPERSEDED")),
            ],
        )
        result = opt.optimize(context)
        assert [i.entity.id for i in result.items] == ["k1"]
        assert len(result.excluded) == 3

    def test_include_history_keeps_all(self) -> None:
        opt = self._optimizer()
        context = ContextDocument(
            task="t", project_id="p1",
            items=[_item(Knowledge(id="k1", title="A", status="ARCHIVED"))],
        )
        result = opt.optimize(context, include_history=True)
        assert len(result.items) == 1

    def test_canonical_merge_by_title(self) -> None:
        opt = self._optimizer()
        context = ContextDocument(
            task="t", project_id="p1",
            items=[
                _item(Knowledge(id="k1", title="UDP FIX", status="CANONICAL"), score=60.0),
                _item(Knowledge(id="k2", title="udp  fix", status="CANONICAL"), score=80.0),
            ],
        )
        result = opt.optimize(context)
        ids = [i.entity.id for i in result.items]
        assert ids == ["k2"]  # остаётся с большим score
        assert any(i.excluded_reason == "canonical_merged" for i in result.excluded)

    def test_order_preserved(self) -> None:
        opt = self._optimizer()
        context = ContextDocument(
            task="t", project_id="p1",
            items=[
                _item(Knowledge(id="k1", title="A"), score=30.0),
                _item(Knowledge(id="k2", title="B"), score=90.0),
            ],
        )
        result = opt.optimize(context)
        assert [i.entity.id for i in result.items] == ["k1", "k2"]

    def test_relation_path_preserved(self) -> None:
        opt = self._optimizer()
        item = _item(Knowledge(id="k1", title="A"))
        item.relation_path = ["r1"]
        context = ContextDocument(task="t", project_id="p1", items=[item])
        result = opt.optimize(context)
        assert result.items[0].relation_path == ["r1"]

    def test_token_budget_drops_lowest(self) -> None:
        opt = self._optimizer(limits={"SMALL": 20})
        long_title = "word " * 100
        context = ContextDocument(
            task="t", project_id="p1", profile="SMALL",
            items=[
                _item(Knowledge(id="k1", title=long_title), score=10.0),
                _item(Knowledge(id="k2", title="short"), score=90.0),
            ],
        )
        result = opt.optimize(context)
        assert any(i.excluded_reason == "token_budget" for i in result.excluded)

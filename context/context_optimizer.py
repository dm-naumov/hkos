"""HKOS Context Optimizer (DS-009 §11, IP-009)
=============================================
Optimizer обязан (IP-009):
- удалить дубликаты;
- убрать ARCHIVED / REJECTED / SUPERSEDED;
- сохранить логический порядок;
- сохранить причинно-следственные связи (relation_path);
- соблюдать Minimal Context Principle (профили SMALL/MEDIUM/LARGE/FULL).

Canonical Merge: канонические знания с одинаковым нормализованным
title объединяются (остаётся с наибольшим score).
"""

import re

from hkos.context.models import ContextDocument, ContextItem
from hkos.context.token_estimator import TokenEstimator
from hkos.services.librarian.knowledge_status import (
    KNOWLEDGE_STATUS_ARCHIVED,
    KNOWLEDGE_STATUS_CANONICAL,
    KNOWLEDGE_STATUS_REJECTED,
    KNOWLEDGE_STATUS_SUPERSEDED,
)

__all__ = ["ContextOptimizer"]

_WS = re.compile(r"\s+")


class ContextOptimizer:
    """Оптимизация контекста (dedup, фильтры, canonical merge, бюджет)."""

    def __init__(
        self,
        estimator: TokenEstimator,
        profile_limits: dict[str, int] | None = None,
    ) -> None:
        """Инициализация оптимизатора.

        Args:
            estimator: TokenEstimator (коэффициенты из конфигурации).
            profile_limits: Лимиты токенов по профилям (из конфигурации).

        """
        self._estimator = estimator
        self._profile_limits = dict(profile_limits or {})

    @staticmethod
    def _normalize_title(item: ContextItem) -> str:
        """Нормализованный title (для canonical merge)."""
        title = getattr(item.entity, "title", "") or getattr(item.entity, "name", "") or ""
        return _WS.sub(" ", title.strip().lower())

    def _is_excluded_status(self, item: ContextItem) -> bool:
        """Статус, исключаемый по умолчанию."""
        status = getattr(item.entity, "status", "") or ""
        return status in (
            KNOWLEDGE_STATUS_ARCHIVED,
            KNOWLEDGE_STATUS_REJECTED,
            KNOWLEDGE_STATUS_SUPERSEDED,
        )

    def optimize(
        self,
        context: ContextDocument,
        include_history: bool = False,
    ) -> ContextDocument:
        """Оптимизировать контекст.

        Args:
            context: Исходный документ контекста.
            include_history: Включить исторические статусы.

        Returns:
            Оптимизированный документ (dedup, фильтры, merge, бюджет).

        """
        result = ContextDocument(
            task=context.task,
            project_id=context.project_id,
            campaign_id=context.campaign_id,
            profile=context.profile,
            snapshot=context.snapshot,
        )

        # 1. Dedup по id + фильтр статусов
        seen: set[str] = set()
        for item in context.items:
            entity_id = getattr(item.entity, "id", "")
            if entity_id in seen:
                result.excluded.append(self._exclude(item, "duplicate"))
                continue
            if not include_history and self._is_excluded_status(item):
                result.excluded.append(
                    self._exclude(item, "status_excluded")
                )
                continue
            seen.add(entity_id)
            result.items.append(item)

        # 2. Canonical Merge: одинаковые нормализованные title канонических
        canonical_by_title: dict[str, ContextItem] = {}
        merged: list[ContextItem] = []
        for item in result.items:
            if (
                getattr(item.entity, "status", "") == KNOWLEDGE_STATUS_CANONICAL
                and self._normalize_title(item)
            ):
                key = self._normalize_title(item)
                existing = canonical_by_title.get(key)
                if existing is None or item.score > existing.score:
                    if existing is not None:
                        merged.remove(existing)
                        result.excluded.append(
                            self._exclude(existing, "canonical_merged")
                        )
                    canonical_by_title[key] = item
                    merged.append(item)
                else:
                    result.excluded.append(
                        self._exclude(item, "canonical_merged")
                    )
            else:
                merged.append(item)
        result.items = merged

        # 3. Minimal Context Principle: бюджет профиля
        limit = self._profile_limits.get(context.profile, 0)
        if limit > 0:
            result = self._apply_budget(result, limit)

        result.estimates = self._estimator.estimate(
            " ".join(
                getattr(i.entity, "title", "") or ""
                for i in result.items
            )
        )
        return result

    def _apply_budget(
        self, context: ContextDocument, limit: int
    ) -> ContextDocument:
        """Отбросить наименее ценные элементы до лимита токенов."""
        # Канонические — приоритет сохранения
        kept: list[ContextItem] = []
        dropped: list[ContextItem] = []
        for item in sorted(
            context.items,
            key=lambda i: (i.score, getattr(i.entity, "id", "")),
            reverse=True,
        ):
            if getattr(item.entity, "status", "") == KNOWLEDGE_STATUS_CANONICAL:
                kept.append(item)
                continue
            probe = kept + [item]
            estimate = self._estimator.estimate(
                " ".join(
                    getattr(i.entity, "title", "") or "" for i in probe
                )
            )
            if estimate.estimated_tokens <= limit:
                kept.append(item)
            else:
                dropped.append(self._exclude(item, "token_budget"))
        kept.sort(key=lambda i: (i.score, getattr(i.entity, "id", "")), reverse=True)
        context.items = kept
        context.excluded.extend(dropped)
        return context

    @staticmethod
    def _exclude(item: ContextItem, reason: str) -> ContextItem:
        """Пометить элемент исключённым (копия)."""
        excluded = ContextItem(
            entity=item.entity,
            entity_type=item.entity_type,
            source=item.source,
            reason=item.reason,
            score=item.score,
            relation_path=list(item.relation_path),
            matched_topic=item.matched_topic,
            matched_keywords=list(item.matched_keywords),
        )
        excluded.excluded_reason = reason
        return excluded

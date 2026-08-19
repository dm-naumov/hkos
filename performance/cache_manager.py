"""HKOS Cache Manager (DS-013 ЭТАП 5)
======================================
Результатный кэш Performance Layer (НЕ IndexCache — тот принадлежит
Index Layer): retrieval results, snapshot loading, serialized context.

Политика: LRU + TTL; настройки: enabled/max_entries/ttl_seconds.

НЕ кэширует: активные изменения, незавершённые операции, результаты LLM.
"""

import threading
import time
from collections import OrderedDict
from typing import Final

__all__ = ["CacheManager"]

_DEFAULT_MAX: Final[int] = 1000
_DEFAULT_TTL: Final[float] = 3600.0


class CacheManager:
    """LRU+TTL кэш (thread-safe)."""

    def __init__(
        self,
        enabled: bool = True,
        max_entries: int = _DEFAULT_MAX,
        ttl_seconds: float = _DEFAULT_TTL,
    ) -> None:
        """Инициализация.

        Args:
            enabled: Включён ли кэш.
            max_entries: Максимум записей (LRU-вытеснение).
            ttl_seconds: Время жизни записи.
        """
        self._enabled = enabled
        self._max_entries = max_entries
        self._ttl = ttl_seconds
        self._lock = threading.RLock()
        self._entries: OrderedDict[str, tuple[float, object]] = OrderedDict()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> object | None:
        """Вернуть значение, если валидно (TTL) — иначе None (удаляет)."""
        if not self._enabled:
            return None
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                self._misses += 1
                return None
            created, value = entry
            if time.monotonic() - created > self._ttl:
                del self._entries[key]
                self._misses += 1
                return None
            self._entries.move_to_end(key)
            self._hits += 1
            return value

    def set(self, key: str, value: object) -> None:
        """Сохранить значение (LRU)."""
        if not self._enabled:
            return
        with self._lock:
            self._entries[key] = (time.monotonic(), value)
            self._entries.move_to_end(key)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)

    def invalidate(self, key: str) -> None:
        """Удалить запись."""
        with self._lock:
            self._entries.pop(key, None)

    def clear(self) -> None:
        """Полная очистка."""
        with self._lock:
            self._entries.clear()

    def statistics(self) -> dict[str, object]:
        """Статистика: hits/misses/hit_ratio/size."""
        with self._lock:
            total = self._hits + self._misses
            return {
                "enabled": self._enabled,
                "size": len(self._entries),
                "hits": self._hits,
                "misses": self._misses,
                "hit_ratio": (self._hits / total) if total else 0.0,
            }

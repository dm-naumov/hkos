"""HKOS Index Cache (DS-013 ЭТАП 3)
====================================
Внутренний кэш Index Layer: хранит РАЗОБРАННЫЙ IndexSnapshot проекта.

- НЕ бизнес-логика: только get/set/invalidate/clear;
- thread-safe: много читателей (get), один писатель (set/invalidate);
- владеет: временем жизни (fingerprint-проверка), инвалидизацией,
  повторным использованием;
- инвалидация: при изменении файлов индекса (mtime/size fingerprint —
  без полного hash на каждый запрос), после update/rebuild (через
  IndexEngine).
"""

import threading
from typing import Final

__all__ = ["IndexCache"]

_FINGERPRINT_MISS: Final[tuple[tuple[str, int, int], ...]] = ()


class IndexCache:
    """Кэш разобранных IndexSnapshot (проект -> snapshot)."""

    def __init__(self, max_entries: int = 256) -> None:
        """Инициализация.

        Args:
            max_entries: Максимум проектов в кэше (FIFO-вытеснение).

        """
        self._lock = threading.RLock()
        self._entries: dict[str, tuple[object, object]] = {}
        self._order: list[str] = []
        self._max_entries = max_entries

    def get(self, key: str, fingerprint: object) -> object | None:
        """Вернуть значение, если оно закэшировано И fingerprint
        совпадает с текущим (иначе None — вызывающий перестроит).

        Args:
            key: Проект (UUID).
            fingerprint: Отпечаток файлов индекса (mtime/size).

        """
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            value, stored = entry
            if stored != fingerprint:
                # внешнее изменение файлов индекса -> инвалидация
                self._entries.pop(key, None)
                if key in self._order:
                    self._order.remove(key)
                return None
            return value

    def set(self, key: str, value: object, fingerprint: object) -> None:
        """Закэшировать разобранный снимок (вытеснение FIFO)."""
        with self._lock:
            if key not in self._entries:
                self._order.append(key)
            self._entries[key] = (value, fingerprint)
            while len(self._order) > self._max_entries:
                oldest = self._order.pop(0)
                self._entries.pop(oldest, None)

    def invalidate(self, key: str) -> None:
        """Инвалидировать проект (после update/rebuild)."""
        with self._lock:
            self._entries.pop(key, None)
            if key in self._order:
                self._order.remove(key)

    def clear(self) -> None:
        """Полная очистка кэша."""
        with self._lock:
            self._entries.clear()
            self._order.clear()

    def size(self) -> int:
        """Количество проектов в кэше."""
        with self._lock:
            return len(self._entries)

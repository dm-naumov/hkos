"""HKOS Resource Monitor (DS-013 ЭТАП 4)
==========================================
Только чтение: RAM, CPU, размеры Repository/Index/Snapshot, размер
кэша индекса. НЕ управляет ресурсами; НЕ изменяет данные.

Overhead <= 10 ms (бюджет DS-013).
"""

import os
import time
from pathlib import Path
from typing import Callable

__all__ = ["ResourceMonitor"]


class ResourceMonitor:
    """Наблюдатель ресурсов (read-only)."""

    def __init__(
        self,
        root: Path,
        cache_size_provider: Callable[[], int] | None = None,
    ) -> None:
        """Инициализация.

        Args:
            root: Корень рабочей области HKOS (для размеров).
            cache_size_provider: Источник размера кэша индекса
                (например, IndexCache.size; DI без зависимостей).
        """
        self._root = Path(root)
        self._cache_size_provider = cache_size_provider
        self._last_cpu = os.times()
        self._last_cpu_at = time.monotonic()

    def snapshot(self) -> dict[str, object]:
        """Текущие показатели (read-only)."""
        return {
            "ram_mb": self._ram_mb(),
            "cpu_percent": self._cpu_percent(),
            "repository_size_bytes": self._dir_size(self._root / "projects"),
            "index_size_bytes": self._index_size(),
            "snapshot_size_bytes": self._snapshot_size(),
            "cache_entries": self._cache_entries(),
        }

    # ---- метрики ----

    def _ram_mb(self) -> float:
        """RSS процесса (страницы * размер страницы)."""
        try:
            with open("/proc/self/statm") as handle:
                fields = handle.read().split()
            pages = int(fields[1])
            return pages * os.sysconf("SC_PAGE_SIZE") / (1024 * 1024)
        except Exception:
            return 0.0

    def _cpu_percent(self) -> float:
        """Загрузка CPU процесса (дельта process_time)."""
        now = os.times()
        elapsed = max(time.monotonic() - self._last_cpu_at, 1e-9)
        cpu_time = (now.user - self._last_cpu.user) + (
            now.system - self._last_cpu.system)
        self._last_cpu = now
        self._last_cpu_at = time.monotonic()
        return cpu_time / elapsed * 100.0

    def _dir_size(self, path: Path) -> int:
        """Размер каталога (сумма размеров файлов; без чтения данных)."""
        if not path.exists():
            return 0
        total = 0
        for current, _dirs, files in os.walk(path):
            for name in files:
                try:
                    total += (Path(current) / name).stat().st_size
                except OSError:
                    continue
        return total

    def _index_size(self) -> int:
        """Размер файлов индексов (projects/*/indexes)."""
        total = 0
        projects = self._root / "projects"
        if not projects.exists():
            return 0
        for project_dir in projects.iterdir():
            total += self._dir_size(project_dir / "indexes")
        return total

    def _snapshot_size(self) -> int:
        """Размер снимков (projects/*/snapshots)."""
        total = 0
        projects = self._root / "projects"
        if not projects.exists():
            return 0
        for project_dir in projects.iterdir():
            total += self._dir_size(project_dir / "snapshots")
        return total

    def _cache_entries(self) -> int:
        """Число записей кэша индекса (через DI-провайдер)."""
        if self._cache_size_provider is None:
            return 0
        try:
            return int(self._cache_size_provider())
        except Exception:
            return 0

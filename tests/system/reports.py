"""HKOS System Reports (DS-014 ЭТАП 5 §14).
================================================================
Утилиты генерации отчётов системных тестов.
"""

from pathlib import Path
from typing import Final

REPORTS_DIR: Final[Path] = Path("/home/dm/Документы/память/Reports/review")


def write_report(name: str, content: str) -> str:
    """Записать отчёт (возвращает путь)."""
    path = REPORTS_DIR / name
    path.write_text(content)
    return str(path)

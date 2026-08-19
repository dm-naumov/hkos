"""HKOS System Reports (DS-014 ЭТАП 5 §14).
================================================================
Утилиты генерации отчётов системных тестов.
"""

import os
import tempfile
from pathlib import Path
from typing import Final

# Report sink dir: override with HKOS_REPORTS_DIR; temp by default (portable).
REPORTS_DIR: Final[Path] = Path(
    os.environ.get("HKOS_REPORTS_DIR",
                   os.path.join(tempfile.gettempdir(), "hkos-reports")))


def write_report(name: str, content: str) -> str:
    """Записать отчёт (возвращает путь)."""
    path = REPORTS_DIR / name
    path.write_text(content)
    return str(path)

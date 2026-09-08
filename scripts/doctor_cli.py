#!/usr/bin/env python3
"""HKOS Doctor CLI — тонкий враппер над дистрибутивным hkos.cli (DS-017 ЭТАП 5).

Обратная совместимость: прежний вызов и exit-коды сохранены.
Usage:
    python3 scripts/doctor_cli.py --project <id|name> [--root <data-root>]

Exit codes: 0 = PASS, 1 = FAIL, 2 = project not found, 3 = internal error.
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    """Делегировать в hkos.cli (команда doctor)."""
    repo_root = Path(__file__).resolve().parent.parent
    # The repository root IS the hkos package; its parent must be on sys.path.
    pkg_parent = str(repo_root.parent)
    if pkg_parent not in sys.path:
        sys.path.insert(0, pkg_parent)

    from hkos.cli import main as cli_main

    # Трансляция аргументов: doctor_cli исторически не имел подкоманды.
    argv = ["doctor"] + [a for a in sys.argv[1:] if a != "doctor"]
    return cli_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())

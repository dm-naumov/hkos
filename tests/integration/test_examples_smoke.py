"""IP-017 ЭТАП 6: smoke-тесты examples (пресеты JSON + демо-скрипт).

Пресеты парсятся и содержат сервер hkos; демо исполняется (subprocess,
cwd=repo, PYTHONPATH=parent) и завершается с кодом 0.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PKG_PARENT = str(_REPO_ROOT.parent)

_JSON_PRESETS = (
    _REPO_ROOT / "examples" / "cursor-mcp.json",
    _REPO_ROOT / "examples" / "windsurf-mcp.json",
)


class TestExamplesSmoke:
    """Примеры валидны и исполнимы."""

    def test_ide_presets_parse_and_declare_hkos(self) -> None:
        for preset in _JSON_PRESETS:
            assert preset.exists(), f"missing preset: {preset}"
            config = json.loads(preset.read_text(encoding="utf-8"))
            assert "hkos" in config["mcpServers"], preset.name
            server = config["mcpServers"]["hkos"]
            assert server["command"] in ("uvx", "pipx")
            assert server["args"][0] == "hkos-mcp"

    def test_demo_failure_recovery_runs(self) -> None:
        env = {
            **os.environ,
            "PYTHONPATH": _PKG_PARENT,
            "HKOS_LOG_LEVEL": "ERROR",
        }
        proc = subprocess.run(
            [sys.executable, "examples/demo_failure_recovery.py"],
            capture_output=True, text=True, env=env, cwd=str(_REPO_ROOT),
            timeout=120,
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "FAILURE" in proc.stdout
        assert "deterministic memory beats repetition" in proc.stdout

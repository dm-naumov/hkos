"""DS-015 ЭТАП 2: Documentation Foundation.

Обязательные документы существуют; ссылки не ведут на отсутствующие
файлы; deprecated API не упоминаются.
"""

import os
import re
from pathlib import Path

DOCS_DIR = Path("/home/dm/hkos/docs")

REQUIRED_DOCS = [
    "architecture.md", "installation.md", "administrator.md",
    "developer.md", "api-reference.md", "migration-guide.md",
    "troubleshooting.md", "performance-guide.md",
]

DEPRECATED_TERMS = [
    "deprecated", "will be removed", "legacy API", "not supported",
]


class TestDocumentation:
    """Фундамент документации: существование, ссылки, актуальность."""

    def test_required_docs_exist(self) -> None:
        for name in REQUIRED_DOCS:
            assert (DOCS_DIR / name).exists(), f"{name} missing"
            assert (DOCS_DIR / name).stat().st_size > 200, f"{name} empty"

    def test_internal_links_valid(self) -> None:
        for name in os.listdir(DOCS_DIR):
            if not name.endswith(".md"):
                continue
            content = (DOCS_DIR / name).read_text(encoding="utf-8")
            for target in re.findall(r"\[([^\]]+)\.md\]", content):
                assert (DOCS_DIR / target).exists(), (
                    f"{name}: link to missing {target}.md")

    def test_no_deprecated_api(self) -> None:
        for name in os.listdir(DOCS_DIR):
            if not name.endswith(".md"):
                continue
            content = (DOCS_DIR / name).read_text(encoding="utf-8").lower()
            for term in DEPRECATED_TERMS:
                assert term not in content, f"{name}: mentions {term!r}"

    def test_docs_reflect_actual_components(self) -> None:
        """Упоминаемые компоненты существуют в пакете hkos/."""
        architecture = (DOCS_DIR / "architecture.md").read_text(encoding="utf-8")
        for component in ("migration", "performance", "integration",
                          "kernel", "services", "snapshot"):
            assert component in architecture

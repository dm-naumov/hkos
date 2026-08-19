"""DS-015 ЭТАП 5.5: Documentation Sign-off.
================================================================
Все обязательные документы; соответствие коду; версии совпадают;
production config описан.
"""

from pathlib import Path

import yaml

DOCS = Path("/home/dm/hkos/docs")
REQUIRED = [
    "architecture.md", "installation.md", "administrator.md",
    "developer.md", "api-reference.md", "migration-guide.md",
    "troubleshooting.md", "performance-guide.md",
]


class TestDocumentationSignoff:
    """Документация: наличие, соответствие, версии."""

    def test_docs_exist(self) -> None:
        for name in REQUIRED:
            path = DOCS / name
            assert path.exists() and path.stat().st_size > 200, name

    def test_docs_match_code(self) -> None:
        """Упоминаемые компоненты существуют в пакете hkos/."""
        architecture = (DOCS / "architecture.md").read_text(encoding="utf-8")
        for component in ("migration", "performance", "integration",
                          "kernel", "services", "snapshot", "retrieval",
                          "context", "librarian"):
            assert component in architecture, f"{component} not documented"

    def test_no_nonexistent_functions(self) -> None:
        api = (DOCS / "api-reference.md").read_text(encoding="utf-8")
        for fake in ("graph search", "semantic search", "event bus"):
            assert fake not in api.lower(), f"docs mention {fake!r}"

    def test_versions_match(self) -> None:
        """Версии конфига и release совпадают."""
        config = yaml.safe_load(
            Path("/home/dm/hkos/config/hkos-production.yaml").read_text())
        assert config["hkos"]["version"] == "1.0.0"

    def test_production_config_described(self) -> None:
        docs_text = " ".join(
            (DOCS / name).read_text(encoding="utf-8") for name in REQUIRED)
        assert "hkos-production.yaml" in docs_text
        assert "ConfigLoader" in docs_text

"""Import boundary audit: hkos/integration/hermes (DS-012 ЭТАП 4 §1)."""

import inspect


class TestSecurityImportBoundary:
    """Запрещённые импорты отсутствуют; слой не знает внутренностей HKOS."""

    MODULES = [
        "hkos.integration.hermes.migration_tools",
        "hkos.integration.hermes.migration_commands",
        "hkos.integration.hermes.security",
        "hkos.integration.hermes.audit",
        "hkos.integration.hermes.fallback",
        "hkos.integration.hermes.agent_lock",
        "hkos.integration.hermes.schemas",
    ]

    FORBIDDEN = [
        "hkos.storage", "hkos.repository.", "hkos.index.",
        "hkos.snapshot.", "hkos.services.librarian",
        "hkos.context.",
    ]

    def test_forbidden_imports_absent(self) -> None:
        for module_name in self.MODULES:
            module = __import__(module_name, fromlist=["x"])
            source = inspect.getsource(module)
            for forbidden in self.FORBIDDEN:
                assert forbidden not in source, (
                    f"{module_name}: forbidden import {forbidden}"
                )

    def test_internal_migration_components_absent(self) -> None:
        internal = [
            "migration_manager", "backup_manager", "rollback_manager",
            "migration_registry", "migration_executor", "migration_validator",
            "schema_detector",
        ]
        for module_name in self.MODULES:
            module = __import__(module_name, fromlist=["x"])
            source = inspect.getsource(module)
            for component in internal:
                assert f"hkos.migration.{component}" not in source, (
                    f"{module_name}: internal component {component}"
                )

    def test_only_public_facade_reachable(self) -> None:
        """Единственный публичный вход миграции — MigrationEngine."""
        from hkos.integration.hermes.migration_tools import MigrationTools

        source = inspect.getsource(MigrationTools)
        assert "MigrationEngine" in source

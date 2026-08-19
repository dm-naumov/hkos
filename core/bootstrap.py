"""HKOS Bootstrap
===============
Performs the startup sequence for HKOS.
"""

from hkos.core.config import ConfigLoader
from hkos.core.engine import HKOSEngine
from hkos.core.health import HealthManager
from hkos.core.logger import HKOSLogger
from hkos.core.registry import Registry
from hkos.core.version import VersionManager


class Bootstrap:
    """Bootstrap handler for HKOS.
    
    Executes the startup sequence:
    1. Load configuration
    2. Validate configuration
    3. Initialize engine
    4. Health check
    5. Ready
    """

    def __init__(self, profile: str = "development") -> None:
        self._profile: str = profile
        self._config: ConfigLoader | None = None
        self._logger: HKOSLogger | None = None
        self._registry: Registry | None = None
        self._version: VersionManager | None = None
        self._health: HealthManager | None = None
        self._engine: HKOSEngine | None = None

    def run(self) -> HKOSEngine:
        """Execute the full bootstrap sequence.
        
        Returns:
            An initialized HKOSEngine instance.
        
        Raises:
            InitializationError if any bootstrap step fails.

        """
        # Step 1: Load config
        self._config = ConfigLoader(profile=self._profile)
        config_data = self._config.load()

        # Step 2: Initialize logger from config
        log_config = config_data.get("logging", {})
        self._logger = HKOSLogger()
        self._logger.initialize(
            level=log_config.get("level", "DEBUG"),
            log_file=log_config.get("file"),
            console=True,
        )
        self._logger.info("Bootstrap: configuration loaded")

        # Step 3: Validate config
        self._config.validate()
        self._logger.info("Bootstrap: configuration validated")

        # Step 4: Create supporting components
        self._registry = Registry()
        self._version = VersionManager()
        self._health = HealthManager()

        self._logger.info(
            f"Bootstrap: version={self._version.version_string}, "
            f"schema={self._version.schema_version}"
        )

        # Step 5: Initialize engine
        self._engine = HKOSEngine(
            config=self._config,
            logger=self._logger,
            registry=self._registry,
            version=self._version,
            health=self._health,
        )

        # Register core components
        self._registry.register("config", self._config, description="Configuration Loader")
        self._registry.register("logger", self._logger, description="HKOS Logger")
        self._registry.register("registry", self._registry, description="Component Registry")
        self._registry.register("version", self._version, description="Version Manager")
        self._registry.register("health", self._health, description="Health Manager")

        # Register health checks
        self._health.register_check("config", ok=self._config.is_loaded)
        self._health.register_check("logger", ok=self._logger.is_initialized)
        self._health.register_check("registry", ok=not self._registry.is_empty)

        self._logger.info("Bootstrap: engine ready")
        return self._engine

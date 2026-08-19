"""Hermes Integration (DS-012).

=============================
Тонкий адаптерный слой между внешним Hermes Agent и публичным фасадом
MigrationEngine (DS-011 §6). Hermes — управляющий слой; доменная логика
остаётся в DS-011.
"""

from hkos.integration.hermes.agent_lock import AgentLock
from hkos.integration.hermes.audit import AuditLogger
from hkos.integration.hermes.doctor import ConsistencyIssue, ConsistencyReport, HkosDoctor
from hkos.integration.hermes.fallback import FallbackPolicy
from hkos.integration.hermes.hooks import HermesProductionHooks
from hkos.integration.hermes.migration_commands import MigrationCommandRegistry
from hkos.integration.hermes.migration_tools import MigrationTools
from hkos.integration.hermes.security import AgentContext, MigrationSafetyGuard

__all__ = [
    "MigrationTools",
    "HermesProductionHooks",
    "MigrationCommandRegistry",
    "AgentContext",
    "MigrationSafetyGuard",
    "AuditLogger",
    "FallbackPolicy",
    "AgentLock",
    "ConsistencyIssue",
    "ConsistencyReport",
    "HkosDoctor",
]

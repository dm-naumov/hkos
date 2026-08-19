"""DS-016: Fixtures (ЭТАП 1).

Hermes-агенты (Planner/Executor/Reviewer) + инженерный корпус:
DECISION/CONFIGURATION/FAILURE знания (только через Librarian).
"""

from hkos.repository.models import Knowledge
from tests.system.ds016.hermes_context import HermesRuntimeContext

__all__ = ["hermes_agents", "seed_engineering_memory"]


def hermes_agents() -> list:
    """Planner/Executor/Reviewer (AgentContext; общая память HKOS)."""
    from hkos.integration.hermes.security import AgentContext

    return [
        AgentContext(agent_id="planner", agent_type="planner"),
        AgentContext(agent_id="executor", agent_type="executor"),
        AgentContext(agent_id="reviewer", agent_type="reviewer"),
    ]


def seed_engineering_memory(
    ctx: HermesRuntimeContext, project_id: str, campaign_id: str
) -> list[str]:
    """Инженерная память: DECISION/CONFIGURATION/FAILURE (через Librarian)."""
    decision = ctx.librarian.register(project_id, Knowledge(
        title="Decision OpenWRT", body="использовать policy routing",
        tags=["openwrt", "routing"], category="DECISION",
        source_campaign=campaign_id))
    configuration = ctx.librarian.register(project_id, Knowledge(
        title="Config AX3000T", body="lan=192.168.1.0/24, wan=pppoe",
        tags=["openwrt", "config"], category="CONFIGURATION",
        source_campaign=campaign_id))
    failure = ctx.librarian.register(project_id, Knowledge(
        title="Failure Routing", body="cause: неправильный routing rule\n"
            "recommendations: использовать policy routing",
        tags=["openwrt", "routing"], kind="negative",
        source_campaign=campaign_id))
    for k in (decision, configuration, failure):
        ctx.librarian.canonicalize(project_id, k.id)
    return [decision.id, configuration.id, failure.id]

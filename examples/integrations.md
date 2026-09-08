# HKOS integrations: LangChain, AutoGen, IDE presets

HKOS ships an MCP server (`hkos-mcp`, stdio, zero dependencies). Any MCP-capable
client connects with a JSON config — no per-client code is needed. Below are the
canonical wiring examples.

Install once:

```bash
pip install hkos            # or: uv tool install hkos / pipx install hkos
hkos-mcp --help
```

The data root is selected by `--root <path>` or the `HKOS_DATA_ROOT`
environment variable (`HKOS_PROFILE` switches development/production config).

Exposed tools: `retrieve`, `context`, `save`, `snapshot`, `doctor`, `status`
(see [docs/mcp.md](../docs/mcp.md) for the reference).

---

## IDE presets (copy-paste)

### Cursor

Copy `cursor-mcp.json` into your project as `.cursor/mcp.json`:

```bash
mkdir -p .cursor && cp examples/cursor-mcp.json .cursor/mcp.json
```

Set `HKOS_DATA_ROOT` in the preset to the absolute path of your data root
(e.g. `./hkos` next to your checkout).

### Windsurf

Copy `windsurf-mcp.json` into your project as `mcp_config.json`:

```bash
cp examples/windsurf-mcp.json mcp_config.json
```

Same `HKOS_DATA_ROOT` note applies.

### Claude Desktop

```json
{ "mcpServers": { "hkos": { "command": "hkos-mcp",
                            "args": ["--root", "/abs/path/data-root"] } } }
```

---

## LangChain (langchain-mcp-adapters)

```python
"""LangChain agent with HKOS memory over MCP (deterministic, offline)."""
import asyncio
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain.agents import create_react_agent, AgentExecutor

async def main() -> None:
    client = MultiServerMCPClient({
        "hkos": {
            "command": "uvx",
            "args": ["hkos-mcp"],
            "transport": "stdio",
            "env": {"HKOS_DATA_ROOT": "/abs/path/data-root"},
        }
    })
    tools = await client.get_tools()
    # tools now contains hkos_retrieve, hkos_context, hkos_save, hkos_doctor ...
    # give the agent a system prompt that calls hkos_retrieve BEFORE acting and
    # hkos_save AFTER an outcome — HKOS does the rest (no LLM in the loop).
    ...
    await client.close()

asyncio.run(main())
```

Rule of thumb for the agent prompt:

> Before starting a task, call `hkos_retrieve` with the task description.
> If the top result is a FAILURE entry, do NOT repeat it. After the task
> finishes, call `hkos_save` with `kind: "negative"` on failure or a
> `category` hint on success — the deterministic classifier assigns the
> category and the response `warnings` tell you if it was overridden.

## AutoGen

```python
"""AutoGen agent with HKOS MCP tools."""
import asyncio
from autogen_core import SingleThreadedAgentRuntime
from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_magentic_one.agents.mcp_client_agent import MCPClientAgent

async def main() -> None:
    mcp_agent = MCPClientAgent(
        name="hkos_memory",
        model_client=OpenAIChatCompletionClient(...),
        tool_metadata=[...],          # see hkos-mcp tools/list
        server_configs=[
            {
                "command": "uvx",
                "args": ["hkos-mcp"],
                "env": {"HKOS_DATA_ROOT": "/abs/path/data-root"},
            }
        ],
    )
    # register mcp_agent in the runtime and let it retrieve/save memory items
    ...

asyncio.run(main())
```

`tool_metadata` can be generated from `hkos-mcp`'s `tools/list` response; the
six tools are `retrieve/context/save/snapshot/doctor/status`.

---

## Zero-LLM guarantee

Both examples only wire transport. Classification, indexing and retrieval stay
inside HKOS and contain no model calls — swap the model, keep the memory.

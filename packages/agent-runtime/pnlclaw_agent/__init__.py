"""pnlclaw_agent -- Agent runtime for quantitative trading workflows.

Public API:
    - ``AgentRuntime`` — core LLM conversation loop
    - ``ToolCatalog`` — tool registry with policy integration
    - ``BaseTool`` / ``ToolResult`` — tool ABC and result type
    - ``AgentContext`` / ``build_system_prompt`` — prompt construction
    - ``ContextManager`` — conversation history management
"""

from pnlclaw_agent.context.manager import ContextManager
from pnlclaw_agent.prompt_builder import AgentContext, build_system_prompt
from pnlclaw_agent.runtime import AgentRuntime
from pnlclaw_agent.tool_catalog import ToolCatalog
from pnlclaw_agent.tools.base import BaseTool, ToolResult

__all__ = [
    "AgentContext",
    "AgentRuntime",
    "BaseTool",
    "ContextManager",
    "ToolCatalog",
    "ToolResult",
    "build_system_prompt",
]

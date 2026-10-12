from copilot.tools.read_tools import READ_TOOLS
from copilot.tools.registry import Tool, ToolContext, ToolInput, ToolRegistry, WriteOutcome
from copilot.tools.write_tools import WRITE_TOOLS

__all__ = ["Tool", "ToolContext", "ToolInput", "ToolRegistry", "WriteOutcome", "default_registry"]


def default_registry() -> ToolRegistry:
    registry = ToolRegistry()
    for tool in READ_TOOLS + WRITE_TOOLS:
        registry.register(tool)
    return registry

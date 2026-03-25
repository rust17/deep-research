from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .log import log


@dataclass
class Tool:
    name: str
    description: str
    func: Callable
    parameters: dict[str, Any]  # JSON Schema for parameters


class ToolRegistry:
    def __init__(self):
        self.tools: dict[str, Tool] = {}
        self._register_default_tools()

    def _register_default_tools(self):
        """Register default tools (search, visit)."""
        from .tools import search, visit

        # Register search
        self.register_function(
            name="search",
            description="Search the internet for information. Returns a list of search results with titles, URLs, and snippets.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query."},
                    "region": {
                        "type": "string",
                        "description": "Region code (e.g., 'wt-wt', 'us-en').",
                        "default": "wt-wt",
                    },
                },
                "required": ["query"],
            },
        )(search)

        # Register visit
        self.register_function(
            name="visit",
            description="Visit a specific URL and return its summarized content.",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The URL to visit."},
                    "goal": {
                        "type": "string",
                        "description": "The specific information you want to extract from this page.",
                    },
                },
                "required": ["url", "goal"],
            },
        )(visit)

    def register(self, tool: Tool):
        """Register a tool instance."""
        if tool.name in self.tools:
            log.warning(f"Tool '{tool.name}' is already registered. Overwriting.")
        self.tools[tool.name] = tool
        log.info(f"Registered tool: {tool.name}")

    def register_function(self, name: str, description: str, parameters: dict[str, Any]):
        """Decorator to register a function as a tool."""

        def decorator(func: Callable):
            tool = Tool(name=name, description=description, func=func, parameters=parameters)
            self.register(tool)
            return func

        return decorator

    def get_tool(self, name: str) -> Tool | None:
        return self.tools.get(name)

    def get_tools_schema(self) -> list[dict[str, Any]]:
        """Return list of tool definitions for LLM (OpenAI format)."""
        schemas = []
        for tool in self.tools.values():
            schemas.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    },
                }
            )
        return schemas

    def execute(self, name: str, arguments: dict[str, Any]) -> Any:
        """Execute a tool by name with arguments."""
        tool = self.get_tool(name)
        if not tool:
            raise ValueError(f"Tool '{name}' not found.")

        try:
            log.info(f"Executing tool '{name}' with args: {arguments}")
            return tool.func(**arguments)
        except Exception as e:
            log.error(f"Error executing tool '{name}': {e}")
            raise e

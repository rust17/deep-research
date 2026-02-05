from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .logs import console


@dataclass
class Tool:
    name: str
    description: str
    func: Callable
    parameters: dict[str, Any]  # JSON Schema for parameters


class ToolRegistry:
    def __init__(self):
        self.tools: dict[str, Tool] = {}

    def register(self, tool: Tool):
        """Register a tool instance."""
        if tool.name in self.tools:
            console.warning(f"Tool '{tool.name}' is already registered. Overwriting.")
        self.tools[tool.name] = tool
        console.info(f"Registered tool: {tool.name}")

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
            console.info(f"Executing tool '{name}' with args: {arguments}")
            return tool.func(**arguments)
        except Exception as e:
            console.error(f"Error executing tool '{name}': {e}")
            raise e

"""Tool catalog with in-memory indexing and token estimation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from cloakroom.contracts import EffectClass


@dataclass
class ToolEntry:
    """A single tool in the catalog."""

    server_id: str
    tool_name: str
    tool_id: str  # Format: "server.tool"
    description: str
    input_schema: dict[str, Any]
    effect: EffectClass
    tokens_approx: int  # Approximate token count for schema


class Catalog:
    """In-memory tool catalog with token estimation."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolEntry] = {}
        self._total_tokens = 0

    def add_tool(
        self,
        server_id: str,
        tool_name: str,
        description: str,
        input_schema: dict[str, Any],
        effect: EffectClass,
    ) -> None:
        """Add a tool to the catalog.

        Args:
            server_id: Identifier of the MCP server
            tool_name: Name of the tool
            description: Tool description
            input_schema: JSON schema for tool parameters
            effect: Effect classification for this tool
        """
        tool_id = f"{server_id}.{tool_name}"

        # Estimate tokens (rough approximation: JSON length / 4)
        import json

        schema_json = json.dumps(input_schema)
        desc_tokens = len(description) // 4
        schema_tokens = len(schema_json) // 4
        tokens_approx = desc_tokens + schema_tokens

        entry = ToolEntry(
            server_id=server_id,
            tool_name=tool_name,
            tool_id=tool_id,
            description=description,
            input_schema=input_schema,
            effect=effect,
            tokens_approx=tokens_approx,
        )

        self._tools[tool_id] = entry
        self._total_tokens += tokens_approx

    def get_tool(self, tool_id: str) -> ToolEntry | None:
        """Get a tool by its ID.

        Args:
            tool_id: Tool identifier (server.tool format)

        Returns:
            Tool entry or None if not found
        """
        return self._tools.get(tool_id)

    def list_all_tools(self) -> list[ToolEntry]:
        """List all tools in the catalog.

        Returns:
            List of all tool entries
        """
        return list(self._tools.values())

    def get_total_tools(self) -> int:
        """Get the total number of tools in the catalog.

        Returns:
            Total tool count
        """
        return len(self._tools)

    def get_total_tokens(self) -> int:
        """Get the approximate total token count for all tools.

        Returns:
            Total approximate tokens
        """
        return self._total_tokens

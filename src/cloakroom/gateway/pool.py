"""Downstream MCP server client pool."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from cloakroom.discovery.catalog import Catalog
from cloakroom.policy.effects import classify_effect


@dataclass
class ServerConfig:
    """Configuration for a downstream MCP server."""

    server_id: str
    command: str
    args: list[str]
    env: dict[str, str] | None = None


class ClientPool:
    """Manages connections to downstream MCP servers."""

    def __init__(self, server_configs: list[ServerConfig]) -> None:
        """Initialize the client pool.

        Args:
            server_configs: List of server configurations to spawn
        """
        self._configs = server_configs
        self._sessions: dict[str, ClientSession] = {}
        self._catalog = Catalog()

    async def start(self) -> None:
        """Start all downstream MCP servers and collect their tool schemas."""
        for config in self._configs:
            try:
                await self._start_server(config)
            except Exception:
                # Continue with other servers even if one fails
                continue

    async def _start_server(self, config: ServerConfig) -> None:
        """Start a single downstream MCP server.

        Args:
            config: Server configuration

        Raises:
            Exception: If server startup fails
        """
        server_params = StdioServerParameters(
            command=config.command,
            args=config.args,
            env=config.env,
        )

        # Start the server and initialize session
        client = stdio_client(server_params)
        read, write = await client.__aenter__()
        session = ClientSession(read, write)
        await session.__aenter__()

        # Initialize the session
        await session.initialize()

        # Collect tool schemas
        tools_result = await session.list_tools()

        # Store session
        self._sessions[config.server_id] = session

        # Add tools to catalog
        for tool in tools_result.tools:
            # Get annotations if available
            annotations_dict: dict[str, Any] = {}
            if hasattr(tool, "annotations") and tool.annotations:
                # MCP tool annotations is a ToolAnnotations object
                # We need to extract the dict representation
                ann = tool.annotations
                if hasattr(ann, "readOnlyHint"):
                    annotations_dict["readOnlyHint"] = ann.readOnlyHint
                if hasattr(ann, "destructiveHint"):
                    annotations_dict["destructiveHint"] = ann.destructiveHint
                if hasattr(ann, "openWorldHint"):
                    annotations_dict["openWorldHint"] = ann.openWorldHint

            # Classify effect
            tool_id = f"{config.server_id}.{tool.name}"
            effect = classify_effect(tool_id=tool_id, annotations=annotations_dict)

            self._catalog.add_tool(
                server_id=config.server_id,
                tool_name=tool.name,
                description=tool.description or "",
                input_schema=tool.input_schema,
                effect=effect,
            )

    async def call_tool(self, tool_id: str, arguments: dict[str, Any]) -> Any:
        """Call a downstream tool.

        Args:
            tool_id: Tool identifier (server.tool format)
            arguments: Tool arguments

        Returns:
            Tool result

        Raises:
            ValueError: If tool_id format is invalid or server not found
            Exception: If tool call fails
        """
        # Parse tool_id
        parts = tool_id.split(".", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid tool_id format: {tool_id} (expected server.tool)")

        server_id, tool_name = parts

        # Get session
        if server_id not in self._sessions:
            raise ValueError(f"Server not found: {server_id}")

        session = self._sessions[server_id]

        # Call tool
        result = await session.call_tool(tool_name, arguments)

        return result

    def get_catalog(self) -> Catalog:
        """Get the tool catalog.

        Returns:
            Tool catalog with all registered tools
        """
        return self._catalog

    async def stop(self) -> None:
        """Stop all downstream MCP servers."""
        import contextlib

        for session in list(self._sessions.values()):
            with contextlib.suppress(Exception):
                await session.__aexit__(None, None, None)

        self._sessions.clear()

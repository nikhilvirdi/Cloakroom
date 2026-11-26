"""Discovery engine integrating catalog, retrieval, and rewriting."""

from __future__ import annotations

from typing import Any

from cloakroom.contracts import CatalogMetrics, EffectClass
from cloakroom.discovery.catalog import Catalog
from cloakroom.discovery.retrieval import BM25Retriever
from cloakroom.discovery.rewriter import create_discovery_response


class DiscoveryEngine:
    """Main discovery engine for tool search and retrieval."""

    def __init__(self, relations: dict[str, list[str]] | None = None) -> None:
        """Initialize discovery engine.

        Args:
            relations: Optional tool relation hints from configuration
        """
        self.catalog = Catalog()
        self.relations = relations or {}
        self._retriever: BM25Retriever | None = None

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
            server_id: MCP server identifier
            tool_name: Tool name
            description: Tool description
            input_schema: JSON schema for tool parameters
            effect: Effect classification
        """
        self.catalog.add_tool(server_id, tool_name, description, input_schema, effect)
        # Invalidate retriever cache - will rebuild on next search
        self._retriever = None

    def build_index(self) -> None:
        """Build or rebuild the BM25 search index."""
        self._retriever = BM25Retriever(self.catalog)

    def discover_tools(self, query: str, max_tools: int = 6) -> dict[str, Any]:
        """Discover tools matching a query.

        Args:
            query: Search query describing the task
            max_tools: Maximum number of tools to return (1-15)

        Returns:
            Discovery response with tool cards and metadata
        """
        # Ensure retriever is built
        if self._retriever is None:
            self.build_index()

        # Clamp max_tools
        max_tools = max(1, min(15, max_tools))

        # Search for tools
        tools = self._retriever.search(query, max_tools) if self._retriever else []

        # Create response
        return create_discovery_response(
            tools=tools,
            total_tools=self.catalog.get_total_tools(),
            total_tokens=self.catalog.get_total_tokens(),
            relations=self.relations,
        )

    def get_tool(self, tool_id: str) -> dict[str, Any] | None:
        """Get a specific tool by ID.

        Args:
            tool_id: Tool identifier (server.tool format)

        Returns:
            Tool entry dict or None if not found
        """
        tool = self.catalog.get_tool(tool_id)
        if not tool:
            return None

        return {
            "tool_id": tool.tool_id,
            "server_id": tool.server_id,
            "tool_name": tool.tool_name,
            "description": tool.description,
            "input_schema": tool.input_schema,
            "effect": tool.effect.value,
        }

    def get_catalog_metrics(self) -> CatalogMetrics:
        """Get catalog metrics for Control Room display.

        Returns:
            Catalog metrics with tool and token counts
        """
        return CatalogMetrics(
            exposed_tools=0,  # Will be updated by gateway based on last discovery
            total_tools=self.catalog.get_total_tools(),
            exposed_tokens_approx=0,  # Will be updated by gateway based on last discovery
            total_tokens_approx=self.catalog.get_total_tokens(),
        )

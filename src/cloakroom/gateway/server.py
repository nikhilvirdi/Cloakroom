"""Front-facing stdio MCP server exposing discovery, invocation and approval tools."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server

from cloakroom.contracts import (
    ApprovalStatus,
    CloakEngineProtocol,
    EffectClass,
    EventBusProtocol,
    GatewayEvent,
)
from cloakroom.discovery.engine import DiscoveryEngine
from cloakroom.gateway.pool import ClientPool
from cloakroom.policy.approval import ApprovalManager
from cloakroom.policy.effects import classify_effect


class GatewayServer:
    """Front-facing MCP server for the Cloakroom gateway."""

    def __init__(
        self,
        client_pool: ClientPool,
        cloak_engine: CloakEngineProtocol,
        discovery_engine: DiscoveryEngine,
        approval_manager: ApprovalManager,
        event_bus: EventBusProtocol,
        config_effect_overrides: dict[str, EffectClass] | None = None,
    ) -> None:
        """Initialize the gateway server.

        Args:
            client_pool: Downstream MCP client pool
            cloak_engine: Privacy pipeline (vault + cloak)
            discovery_engine: Tool discovery engine
            approval_manager: Approval manager
            event_bus: Event bus for Control Room
            config_effect_overrides: User-configured effect overrides
        """
        self._pool = client_pool
        self._cloak = cloak_engine
        self._discovery = discovery_engine
        self._approvals = approval_manager
        self._event_bus = event_bus
        self._effect_overrides = config_effect_overrides or {}

        # Approval execution cache: approval_id -> cloaked result
        self._approval_results: dict[str, Any] = {}

        # Event counter for unique IDs
        self._event_counter = 0

    def _generate_event_id(self) -> str:
        """Generate unique event ID."""
        self._event_counter += 1
        return f"evt_{self._event_counter:06d}"

    async def _publish_event(
        self,
        event_type: str,
        tool_id: str | None = None,
        effect: EffectClass | None = None,
        cloud_view: Any = None,
        local_view: Any = None,
        entities: list[Any] | None = None,
        latency_ms: float = 0.0,
        tripwire_passed: bool = True,
        decision: str | None = None,
        approval: Any = None,
        catalog_metrics: Any = None,
    ) -> None:
        """Publish an event to the event bus.

        Args:
            event_type: Event type
            tool_id: Tool identifier
            effect: Effect classification
            cloud_view: Cloaked data for cloud
            local_view: Cloaked data for local display
            entities: Cloaked entities
            latency_ms: Latency in milliseconds
            tripwire_passed: Whether tripwire passed
            decision: Decision string
            approval: Approval request
            catalog_metrics: Catalog metrics
        """
        event = GatewayEvent(
            event_id=self._generate_event_id(),
            event_type=event_type,
            timestamp=datetime.now(UTC),
            tool_id=tool_id,
            effect=effect,
            cloud_view=cloud_view,
            local_view=local_view,
            entities=entities or [],
            latency_ms=latency_ms,
            tripwire_passed=tripwire_passed,
            decision=decision,
            approval=approval,
            catalog_metrics=catalog_metrics,
        )

        await self._event_bus.publish(event)

    async def discover_tools(self, query: str, max_tools: int = 6) -> dict[str, Any]:
        """Discover relevant tools based on query.

        Args:
            query: Natural language query
            max_tools: Maximum tools to return

        Returns:
            Discovery result with tools and metrics
        """
        # Get discovery results
        result = self._discovery.discover_tools(query, max_tools=max_tools)

        # Publish discovery event
        catalog_metrics = self._discovery.get_catalog_metrics()
        await self._publish_event(
            event_type="discovery",
            catalog_metrics=catalog_metrics,
        )

        return result

    async def invoke_tool(self, tool_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Invoke a tool through the privacy pipeline.

        Args:
            tool_id: Tool identifier (server.tool format)
            arguments: Tool arguments (may contain placeholders)

        Returns:
            Invocation result (cloaked or pending approval)
        """
        start_time = datetime.now(UTC)

        try:
            # Step 1: Restore placeholders to real values
            restore_result = self._cloak.restore(arguments)

            # Step 1a: Check for blocked (invented/unknown placeholders)
            if restore_result.blocked:
                error_msg = (
                    f"Invalid placeholders detected: {', '.join(restore_result.unknown_placeholders)}. "
                    f"Valid placeholder types: PERSON, EMAIL, ACCT, MED_ID, ORG, PHONE, GOVID, ADDR, SECRET."
                )

                await self._publish_event(
                    event_type="error",
                    tool_id=tool_id,
                    decision="blocked_unknown_placeholders",
                )

                return {
                    "status": "error",
                    "error": error_msg,
                }

            # Step 2: Classify effect
            tool_info = self._discovery.get_tool(tool_id)
            if tool_info is None:
                raise ValueError(f"Tool not found: {tool_id}")

            effect = classify_effect(
                tool_id=tool_id,
                annotations=None,  # Will be from tool_info when available
                config_overrides=self._effect_overrides,
            )

            # Step 3: Check if approval required (EXTERNAL or UNKNOWN)
            if effect in [EffectClass.EXTERNAL, EffectClass.UNKNOWN]:
                # Request approval (wait up to 30s for decision)
                approval_request, decision_received = await self._approvals.request_approval(
                    tool_id=tool_id,
                    effect=effect,
                    restored_arguments=restore_result.restored_arguments,
                    cloaked_arguments=arguments,
                    contains_identifier_tier=restore_result.contains_identifier_tier,
                    identifier_placeholders=[
                        e.placeholder for e in restore_result.used_placeholders
                    ],
                )

                # Publish approval requested event
                await self._publish_event(
                    event_type="approval_requested",
                    tool_id=tool_id,
                    effect=effect,
                    approval=approval_request,
                )

                if not decision_received:
                    # No decision within wait timeout - return pending
                    return {
                        "status": "pending_approval",
                        "approval_id": approval_request.approval_id,
                        "message": "Approval required. Use inspect_status to check outcome.",
                    }

                # Decision received during wait
                if approval_request.status != ApprovalStatus.APPROVED:
                    # Denied or expired
                    await self._publish_event(
                        event_type="approval_resolved",
                        tool_id=tool_id,
                        effect=effect,
                        decision=approval_request.status,
                        approval=approval_request,
                    )

                    return {
                        "status": "denied",
                        "reason": approval_request.status,
                        "message": f"Tool invocation {approval_request.status}",
                    }

                # Approved - continue to execution

            # Step 4: Execute downstream tool call
            downstream_result = await self._pool.call_tool(
                tool_id, restore_result.restored_arguments
            )

            # Step 5: Cloak the result
            cloak_result = self._cloak.cloak(
                downstream_result,
                server_id=tool_id.split(".")[0],
                tool_name=tool_id.split(".")[1],
            )

            # Calculate latency
            latency_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000

            # Step 6: Publish event
            await self._publish_event(
                event_type="tool_call",
                tool_id=tool_id,
                effect=effect,
                cloud_view=cloak_result.cloaked_payload,
                local_view=arguments,  # Show cloaked arguments
                entities=cloak_result.entities,
                latency_ms=latency_ms,
                tripwire_passed=cloak_result.tripwire_passed,
            )

            return {
                "status": "success",
                "result": cloak_result.cloaked_payload,
                "tripwire_passed": cloak_result.tripwire_passed,
                "withheld": cloak_result.withheld,
            }

        except Exception as error:
            await self._publish_event(
                event_type="error",
                tool_id=tool_id,
                decision=f"error: {error!s}",
            )

            return {
                "status": "error",
                "error": str(error),
            }

    async def inspect_status(self, approval_id: str | None = None) -> dict[str, Any]:
        """Inspect approval status or list all pending approvals.

        Args:
            approval_id: Approval ID to inspect (None = list all pending)

        Returns:
            Approval status or list of pending approvals
        """
        if approval_id is None:
            # List all pending approvals
            pending = self._approvals.list_pending()

            return {
                "pending_approvals": [
                    {
                        "approval_id": req.approval_id,
                        "tool_id": req.tool_id,
                        "effect": req.effect,
                        "risk_flags": req.risk_flags,
                        "created_at": req.created_at.isoformat(),
                        "status": req.status,
                    }
                    for req in pending
                ],
            }

        # Inspect specific approval
        return {
            "approval_id": approval_id,
            "status": "pending",
            "message": "Approval status inspection (placeholder implementation)",
        }


def create_mcp_server(gateway: GatewayServer) -> Server:
    """Create MCP server with gateway tools.

    Args:
        gateway: Gateway server instance

    Returns:
        MCP Server instance
    """
    server = Server("cloakroom")

    @server.list_tools()  # type: ignore[attr-defined,untyped-decorator]
    async def list_tools() -> list[Any]:
        """List available meta-tools."""
        return [
            {
                "name": "discover_tools",
                "description": "Discover relevant tools based on natural language query",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Natural language query describing what you want to do",
                        },
                        "max_tools": {
                            "type": "integer",
                            "description": "Maximum number of tools to return (default: 6)",
                            "default": 6,
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "invoke_tool",
                "description": "Invoke a tool through the privacy pipeline. Placeholders like [EMAIL_1] are accepted.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "tool_id": {
                            "type": "string",
                            "description": "Tool identifier from discovery (server.tool format)",
                        },
                        "arguments": {
                            "type": "object",
                            "description": "Tool arguments. May contain placeholders.",
                        },
                    },
                    "required": ["tool_id", "arguments"],
                },
            },
            {
                "name": "inspect_status",
                "description": "Inspect approval status or list pending approvals",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "approval_id": {
                            "type": "string",
                            "description": "Approval ID to inspect (omit to list all pending)",
                        },
                    },
                },
            },
        ]

    @server.call_tool()  # type: ignore[attr-defined,untyped-decorator]
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[Any]:
        """Route tool calls to gateway."""
        if name == "discover_tools":
            result = await gateway.discover_tools(
                query=arguments["query"],
                max_tools=arguments.get("max_tools", 6),
            )
            return [{"type": "text", "text": str(result)}]

        if name == "invoke_tool":
            result = await gateway.invoke_tool(
                tool_id=arguments["tool_id"],
                arguments=arguments["arguments"],
            )
            return [{"type": "text", "text": str(result)}]

        if name == "inspect_status":
            result = await gateway.inspect_status(
                approval_id=arguments.get("approval_id"),
            )
            return [{"type": "text", "text": str(result)}]

        raise ValueError(f"Unknown tool: {name}")

    return server


async def run_gateway_server(gateway: GatewayServer) -> None:
    """Run the gateway MCP server on stdio.

    Args:
        gateway: Gateway server instance
    """
    server = create_mcp_server(gateway)

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())

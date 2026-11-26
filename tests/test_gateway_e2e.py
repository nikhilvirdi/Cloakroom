"""End-to-end tests for the gateway with privacy pipeline and policy enforcement."""

from __future__ import annotations

import pytest

from cloakroom.contracts import EffectClass
from cloakroom.discovery.catalog import Catalog
from cloakroom.discovery.engine import DiscoveryEngine
from cloakroom.gateway.server import GatewayServer
from cloakroom.gateway.test_doubles import DummyCloakEngine, DummyEventBus
from cloakroom.policy.approval import ApprovalManager


class DummyClientPool:
    """Test double for ClientPool - returns canned responses."""

    def __init__(self) -> None:
        """Initialize dummy client pool."""
        self.call_history: list[tuple[str, dict]] = []

    async def call_tool(self, tool_id: str, arguments: dict) -> dict:
        """Record call and return dummy result.

        Args:
            tool_id: Tool identifier
            arguments: Tool arguments

        Returns:
            Dummy result
        """
        self.call_history.append((tool_id, arguments))

        # Return dummy responses based on tool_id
        if "read_text" in tool_id:
            return {"content": "Sample document content with patient data"}
        elif "query_transactions" in tool_id:
            return {"transactions": [{"amount": 52000, "date": "2026-10-15"}]}
        elif "lookup_email" in tool_id:
            return {"email": "billing@lakeview.example", "name": "Lakeview Hospital Billing"}
        elif "create_draft" in tool_id:
            return {"draft_id": "draft_001", "status": "created"}
        elif "send_draft" in tool_id:
            return {"status": "sent", "message_id": "msg_001"}

        return {"result": "dummy_response"}

    def get_catalog(self) -> Catalog:
        """Get dummy catalog with test tools.

        Returns:
            Catalog with test tools
        """
        catalog = Catalog()

        # Add read-only tools
        catalog.add_tool(
            server_id="documents",
            tool_name="read_text",
            description="Read a text document",
            input_schema={"type": "object", "properties": {"filename": {"type": "string"}}},
            effect=EffectClass.READ,
        )

        catalog.add_tool(
            server_id="bank",
            tool_name="query_transactions",
            description="Query bank transactions",
            input_schema={"type": "object", "properties": {"account": {"type": "string"}}},
            effect=EffectClass.READ,
        )

        # Add local write tool
        catalog.add_tool(
            server_id="mail_drafts",
            tool_name="create_draft",
            description="Create email draft",
            input_schema={
                "type": "object",
                "properties": {"to": {"type": "string"}, "body": {"type": "string"}},
            },
            effect=EffectClass.LOCAL_WRITE,
        )

        # Add external tool (requires approval)
        catalog.add_tool(
            server_id="mail_drafts",
            tool_name="send_draft",
            description="Send email draft to external recipient",
            input_schema={"type": "object", "properties": {"draft_id": {"type": "string"}}},
            effect=EffectClass.EXTERNAL,
        )

        return catalog


@pytest.fixture
def gateway_components() -> tuple:
    """Create gateway components for testing.

    Returns:
        Tuple of (client_pool, cloak_engine, discovery_engine, approval_manager, event_bus)
    """
    client_pool = DummyClientPool()
    cloak_engine = DummyCloakEngine()
    event_bus = DummyEventBus()

    # Create discovery engine with catalog
    catalog = client_pool.get_catalog()
    discovery_engine = DiscoveryEngine(relations=None)
    discovery_engine.catalog = catalog

    # Create approval manager with known contacts
    approval_manager = ApprovalManager(
        wait_timeout=0.1,  # Fast timeout for tests
        approval_expiry=1.0,
        known_contacts={"billing@lakeview.example"},
    )

    return client_pool, cloak_engine, discovery_engine, approval_manager, event_bus


@pytest.fixture
def gateway(gateway_components: tuple) -> GatewayServer:
    """Create configured gateway server.

    Args:
        gateway_components: Gateway components fixture

    Returns:
        Configured GatewayServer
    """
    client_pool, cloak_engine, discovery_engine, approval_manager, event_bus = gateway_components

    return GatewayServer(
        client_pool=client_pool,
        cloak_engine=cloak_engine,
        discovery_engine=discovery_engine,
        approval_manager=approval_manager,
        event_bus=event_bus,
    )


class TestGatewayDiscovery:
    """Test tool discovery through gateway."""

    @pytest.mark.asyncio
    async def test_discover_tools(self, gateway: GatewayServer) -> None:
        """Discovery returns relevant tools."""
        result = await gateway.discover_tools("read documents and bank transactions", max_tools=4)

        assert "tools" in result
        tools = result["tools"]
        assert len(tools) > 0

        # Should include document and bank tools
        tool_ids = [t["tool_id"] for t in tools]
        assert any("documents" in tid for tid in tool_ids)


class TestGatewayReadTools:
    """Test READ-effect tools (auto-allow)."""

    @pytest.mark.asyncio
    async def test_read_tool_executes_without_approval(
        self, gateway: GatewayServer, gateway_components: tuple
    ) -> None:
        """READ tools execute immediately without approval."""
        client_pool = gateway_components[0]

        result = await gateway.invoke_tool(
            "documents.read_text",
            {"filename": "test.md"},
        )

        # Should succeed immediately
        assert result["status"] == "success"

        # Should have called downstream
        assert len(client_pool.call_history) == 1
        assert client_pool.call_history[0][0] == "documents.read_text"


class TestGatewayLocalWriteTools:
    """Test LOCAL_WRITE-effect tools (auto-allow)."""

    @pytest.mark.asyncio
    async def test_local_write_executes_without_approval(
        self, gateway: GatewayServer, gateway_components: tuple
    ) -> None:
        """LOCAL_WRITE tools execute immediately without approval."""
        client_pool = gateway_components[0]

        result = await gateway.invoke_tool(
            "mail_drafts.create_draft",
            {"to": "test@example.com", "body": "Test draft"},
        )

        # Should succeed immediately
        assert result["status"] == "success"

        # Should have called downstream
        assert len(client_pool.call_history) == 1
        assert client_pool.call_history[0][0] == "mail_drafts.create_draft"


class TestGatewayExternalTools:
    """Test EXTERNAL-effect tools (require approval)."""

    @pytest.mark.asyncio
    async def test_external_tool_requires_approval(
        self, gateway: GatewayServer, gateway_components: tuple
    ) -> None:
        """EXTERNAL tools wait for approval."""
        client_pool = gateway_components[0]

        result = await gateway.invoke_tool(
            "mail_drafts.send_draft",
            {"draft_id": "draft_001"},
        )

        # Should return pending (no approval within 0.1s timeout)
        assert result["status"] == "pending_approval"
        assert "approval_id" in result

        # Should NOT have called downstream yet
        assert len(client_pool.call_history) == 0

    @pytest.mark.asyncio
    async def test_external_tool_approved_executes(
        self, gateway: GatewayServer, gateway_components: tuple
    ) -> None:
        """Approved EXTERNAL tools execute."""
        import asyncio

        client_pool, _, _, approval_manager, _ = gateway_components

        # Start invocation in background
        task = asyncio.create_task(
            gateway.invoke_tool(
                "mail_drafts.send_draft",
                {"draft_id": "draft_001", "to": "billing@lakeview.example"},
            )
        )

        # Wait for approval to be created
        await asyncio.sleep(0.01)

        # Approve it
        pending = approval_manager.list_pending()
        assert len(pending) == 1

        await approval_manager.resolve(
            pending[0].approval_id,
            approved=True,
            payload_hash=pending[0].payload_hash,
        )

        # Task should complete with success
        result = await task
        assert result["status"] == "success"

        # Should have called downstream
        assert len(client_pool.call_history) == 1


class TestGatewayBlockedPlaceholders:
    """Test unknown placeholder blocking."""

    @pytest.mark.asyncio
    async def test_unknown_placeholder_blocks_execution(
        self, gateway: GatewayServer, gateway_components: tuple
    ) -> None:
        """Unknown placeholders block execution before downstream call."""
        client_pool = gateway_components[0]

        # Try to invoke with invented placeholder
        result = await gateway.invoke_tool(
            "documents.read_text",
            {"filename": "Contains [INVENTED_99] placeholder"},
        )

        # Should be blocked
        assert result["status"] == "error"
        assert "Invalid placeholders" in result["error"]
        assert "INVENTED" in result["error"]

        # Should list valid types
        assert "PERSON" in result["error"]
        assert "EMAIL" in result["error"]

        # Should NOT have called downstream
        assert len(client_pool.call_history) == 0


class TestGatewayRiskFlags:
    """Test risk flag detection."""

    @pytest.mark.asyncio
    async def test_unknown_recipient_flagged(
        self, gateway: GatewayServer, gateway_components: tuple
    ) -> None:
        """Unknown recipients trigger risk flags."""
        _, _, _, approval_manager, _ = gateway_components

        # Try to send to unknown recipient
        result = await gateway.invoke_tool(
            "mail_drafts.send_draft",
            {
                "draft_id": "draft_001",
                "to": "unknown@external-audit.example",
                "body": "Test",
            },
        )

        # Should be pending approval
        assert result["status"] == "pending_approval"

        # Check approval has risk flag
        pending = approval_manager.list_pending()
        assert len(pending) == 1
        assert "UNKNOWN_RECIPIENT" in pending[0].risk_flags


class TestGatewayEventPublishing:
    """Test event bus publishing."""

    @pytest.mark.asyncio
    async def test_events_published_on_discovery(
        self, gateway: GatewayServer, gateway_components: tuple
    ) -> None:
        """Discovery publishes events."""
        event_bus = gateway_components[4]

        await gateway.discover_tools("test query", max_tools=3)

        # Should have published discovery event
        history = event_bus.get_history()
        assert len(history) == 1
        assert history[0].event_type == "discovery"

    @pytest.mark.asyncio
    async def test_events_published_on_tool_call(
        self, gateway: GatewayServer, gateway_components: tuple
    ) -> None:
        """Tool calls publish events."""
        event_bus = gateway_components[4]

        await gateway.invoke_tool("documents.read_text", {"filename": "test.md"})

        # Should have published tool_call event
        history = event_bus.get_history()
        assert len(history) == 1
        assert history[0].event_type == "tool_call"
        assert history[0].tool_id == "documents.read_text"

    @pytest.mark.asyncio
    async def test_no_raw_pii_in_events(
        self, gateway: GatewayServer, gateway_components: tuple
    ) -> None:
        """Events contain only cloaked data, never raw PII."""
        event_bus = gateway_components[4]

        await gateway.invoke_tool(
            "documents.read_text",
            {"filename": "Contains sensitive data"},
        )

        # Check event
        history = event_bus.get_history()
        assert len(history) == 1

        event = history[0]

        # cloud_view should be cloaked
        assert event.cloud_view is not None

        # local_view should be cloaked arguments (what we sent)
        assert event.local_view == {"filename": "Contains sensitive data"}

        # Should NOT contain raw_payload
        # (raw_payload is never published to events per architecture)


class TestGatewayInspectStatus:
    """Test approval status inspection."""

    @pytest.mark.asyncio
    async def test_list_pending_approvals(self, gateway: GatewayServer) -> None:
        """inspect_status lists pending approvals."""
        # Create a pending approval
        await gateway.invoke_tool(
            "mail_drafts.send_draft",
            {"draft_id": "draft_001", "to": "unknown@example.com"},
        )

        # List pending
        result = await gateway.inspect_status()

        assert "pending_approvals" in result
        assert len(result["pending_approvals"]) == 1

        approval = result["pending_approvals"][0]
        assert "approval_id" in approval
        assert approval["tool_id"] == "mail_drafts.send_draft"
        assert approval["effect"] == EffectClass.EXTERNAL

"""Comprehensive tests for the controlroom module."""

import asyncio
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from cloakroom.contracts import (
    ApprovalRequest,
    ApprovalStatus,
    CloakedEntity,
    EffectClass,
    GatewayEvent,
)
from cloakroom.controlroom import (
    ApprovalResolver,
    EventBus,
    create_control_room_app,
    generate_token,
)
from cloakroom.errors import PolicyError


class TestEventBus:
    """Test event bus functionality."""

    @pytest.mark.asyncio
    async def test_publish_and_subscribe(self) -> None:
        bus = EventBus()
        queue = bus.subscribe()

        event = GatewayEvent(
            event_id=str(uuid.uuid4()),
            event_type="test",
            timestamp=datetime.now(UTC),
        )

        await bus.publish(event)

        received = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert received.event_id == event.event_id
        assert received.event_type == "test"

    @pytest.mark.asyncio
    async def test_multiple_subscribers(self) -> None:
        bus = EventBus()
        queue1 = bus.subscribe()
        queue2 = bus.subscribe()

        event = GatewayEvent(
            event_id=str(uuid.uuid4()),
            event_type="test",
            timestamp=datetime.now(UTC),
        )

        await bus.publish(event)

        received1 = await asyncio.wait_for(queue1.get(), timeout=1.0)
        received2 = await asyncio.wait_for(queue2.get(), timeout=1.0)

        assert received1.event_id == event.event_id
        assert received2.event_id == event.event_id

    @pytest.mark.asyncio
    async def test_unsubscribe(self) -> None:
        bus = EventBus()
        queue = bus.subscribe()
        bus.unsubscribe(queue)

        event = GatewayEvent(
            event_id=str(uuid.uuid4()),
            event_type="test",
            timestamp=datetime.now(UTC),
        )

        await bus.publish(event)

        # Queue should be empty since we unsubscribed
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(queue.get(), timeout=0.1)

    def test_get_history(self) -> None:
        """Test get_history (synchronous test)."""
        bus = EventBus()

        # Need to use asyncio loop for async publish
        async def publish_events() -> None:
            for i in range(5):
                event = GatewayEvent(
                    event_id=str(uuid.uuid4()),
                    event_type=f"test_{i}",
                    timestamp=datetime.now(UTC),
                )
                await bus.publish(event)

        # Run in new event loop
        loop = asyncio.new_event_loop()
        loop.run_until_complete(publish_events())
        loop.close()

        history = bus.get_history()
        assert len(history) == 5
        assert all(e.event_type.startswith("test_") for e in history)

    def test_history_max_limit(self) -> None:
        """Test history max limit (synchronous test)."""
        bus = EventBus()

        async def publish_many_events() -> None:
            # Publish more than max history (1000)
            for i in range(1100):
                event = GatewayEvent(
                    event_id=str(uuid.uuid4()),
                    event_type=f"test_{i}",
                    timestamp=datetime.now(UTC),
                )
                await bus.publish(event)

        loop = asyncio.new_event_loop()
        loop.run_until_complete(publish_many_events())
        loop.close()

        history = bus.get_history()
        assert len(history) == 1000  # Should be capped at max

    @pytest.mark.asyncio
    async def test_audit_persistence(self, tmp_path: Path) -> None:
        audit_db = tmp_path / "audit.db"
        bus = EventBus(audit_db_path=audit_db)

        event = GatewayEvent(
            event_id=str(uuid.uuid4()),
            event_type="tool_call",
            timestamp=datetime.now(UTC),
            tool_id="test.tool",
            effect=EffectClass.READ,
            cloud_view={"test": "data"},
            entities=[
                CloakedEntity(
                    placeholder="[PERSON_1]",
                    entity_type="PERSON",
                    tier="contextual",
                    stage="test",
                )
            ],
            latency_ms=10.5,
            tripwire_passed=True,
        )

        await bus.publish(event)

        # Verify audit log was created
        assert audit_db.exists()


class TestApprovalResolver:
    """Test approval resolver functionality."""

    @pytest.mark.asyncio
    async def test_add_and_list_pending(self) -> None:
        resolver = ApprovalResolver()

        approval = ApprovalRequest(
            approval_id="test_001",
            tool_id="test.tool",
            effect=EffectClass.EXTERNAL,
            payload_hash="abc123",
            restored_arguments={"key": "value"},
            cloaked_arguments={"key": "[PERSON_1]"},
            risk_flags=["TEST_FLAG"],
            created_at=datetime.now(UTC),
            status=ApprovalStatus.PENDING,
        )

        resolver.add_pending(approval)
        pending = resolver.list_pending()

        assert len(pending) == 1
        assert pending[0].approval_id == "test_001"

    @pytest.mark.asyncio
    async def test_approve(self) -> None:
        resolver = ApprovalResolver()

        approval = ApprovalRequest(
            approval_id="test_002",
            tool_id="test.tool",
            effect=EffectClass.EXTERNAL,
            payload_hash="def456",
            restored_arguments={"key": "value"},
            cloaked_arguments={"key": "[PERSON_1]"},
            risk_flags=[],
            created_at=datetime.now(UTC),
            status=ApprovalStatus.PENDING,
        )

        resolver.add_pending(approval)
        updated = await resolver.resolve("test_002", approved=True, payload_hash="def456")

        assert updated.status == ApprovalStatus.APPROVED
        assert len(resolver.list_pending()) == 0  # Removed from pending

    @pytest.mark.asyncio
    async def test_deny(self) -> None:
        resolver = ApprovalResolver()

        approval = ApprovalRequest(
            approval_id="test_003",
            tool_id="test.tool",
            effect=EffectClass.EXTERNAL,
            payload_hash="ghi789",
            restored_arguments={"key": "value"},
            cloaked_arguments={"key": "[PERSON_1]"},
            risk_flags=[],
            created_at=datetime.now(UTC),
            status=ApprovalStatus.PENDING,
        )

        resolver.add_pending(approval)
        updated = await resolver.resolve("test_003", approved=False, payload_hash="ghi789")

        assert updated.status == ApprovalStatus.DENIED
        assert len(resolver.list_pending()) == 0

    @pytest.mark.asyncio
    async def test_hash_mismatch_raises_error(self) -> None:
        resolver = ApprovalResolver()

        approval = ApprovalRequest(
            approval_id="test_004",
            tool_id="test.tool",
            effect=EffectClass.EXTERNAL,
            payload_hash="correct_hash",
            restored_arguments={"key": "value"},
            cloaked_arguments={"key": "[PERSON_1]"},
            risk_flags=[],
            created_at=datetime.now(UTC),
            status=ApprovalStatus.PENDING,
        )

        resolver.add_pending(approval)

        with pytest.raises(PolicyError):
            await resolver.resolve("test_004", approved=True, payload_hash="wrong_hash")

    @pytest.mark.asyncio
    async def test_unknown_approval_raises_error(self) -> None:
        resolver = ApprovalResolver()

        with pytest.raises(PolicyError):
            await resolver.resolve("nonexistent", approved=True, payload_hash="any")

    def test_get_approval(self) -> None:
        resolver = ApprovalResolver()

        approval = ApprovalRequest(
            approval_id="test_005",
            tool_id="test.tool",
            effect=EffectClass.EXTERNAL,
            payload_hash="hash",
            restored_arguments={},
            cloaked_arguments={},
            risk_flags=[],
            created_at=datetime.now(UTC),
            status=ApprovalStatus.PENDING,
        )

        resolver.add_pending(approval)

        retrieved = resolver.get_approval("test_005")
        assert retrieved is not None
        assert retrieved.approval_id == "test_005"

        nonexistent = resolver.get_approval("nonexistent")
        assert nonexistent is None


class TestControlRoomApp:
    """Test FastAPI Control Room application."""

    @pytest.mark.asyncio
    async def test_serve_ui(self) -> None:
        bus = EventBus()
        approvals = ApprovalResolver()
        token = "test_token_123"

        app = create_control_room_app(event_bus=bus, approvals=approvals, token=token)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/", params={"token": token})
            assert response.status_code == 200
            assert "Cloakroom Control Room" in response.text
            assert token in response.text  # Token injected

    @pytest.mark.asyncio
    async def test_ui_requires_auth(self) -> None:
        bus = EventBus()
        approvals = ApprovalResolver()
        token = "test_token_123"

        app = create_control_room_app(event_bus=bus, approvals=approvals, token=token)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/", params={"token": "wrong_token"})
            assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_get_state(self) -> None:
        bus = EventBus()
        approvals = ApprovalResolver()
        token = "test_token_123"

        # Add event to history
        event = GatewayEvent(
            event_id=str(uuid.uuid4()),
            event_type="test",
            timestamp=datetime.now(UTC),
            tool_id="test.tool",
            effect=EffectClass.READ,
            latency_ms=10.0,
        )
        await bus.publish(event)

        # Add pending approval
        approval = ApprovalRequest(
            approval_id="test_006",
            tool_id="test.tool",
            effect=EffectClass.EXTERNAL,
            payload_hash="hash",
            restored_arguments={},
            cloaked_arguments={},
            risk_flags=[],
            created_at=datetime.now(UTC),
            status=ApprovalStatus.PENDING,
        )
        approvals.add_pending(approval)

        app = create_control_room_app(event_bus=bus, approvals=approvals, token=token)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/state", params={"token": token})
            assert response.status_code == 200

            data = response.json()
            assert "history" in data
            assert "pending_approvals" in data
            assert len(data["history"]) == 1
            assert len(data["pending_approvals"]) == 1

    @pytest.mark.asyncio
    async def test_make_approval_decision(self) -> None:
        bus = EventBus()
        approvals = ApprovalResolver()
        token = "test_token_123"

        approval = ApprovalRequest(
            approval_id="test_007",
            tool_id="test.tool",
            effect=EffectClass.EXTERNAL,
            payload_hash="test_hash",
            restored_arguments={},
            cloaked_arguments={},
            risk_flags=[],
            created_at=datetime.now(UTC),
            status=ApprovalStatus.PENDING,
        )
        approvals.add_pending(approval)

        app = create_control_room_app(event_bus=bus, approvals=approvals, token=token)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/approvals/test_007/decision",
                params={"token": token},
                json={"approved": True, "payload_hash": "test_hash"},
            )
            assert response.status_code == 200

            data = response.json()
            assert data["status"] == "approved"
            assert len(approvals.list_pending()) == 0

    @pytest.mark.asyncio
    async def test_get_approval_details(self) -> None:
        bus = EventBus()
        approvals = ApprovalResolver()
        token = "test_token_123"

        approval = ApprovalRequest(
            approval_id="test_008",
            tool_id="test.tool",
            effect=EffectClass.EXTERNAL,
            payload_hash="hash",
            restored_arguments={"real": "value"},
            cloaked_arguments={"real": "[PERSON_1]"},
            risk_flags=["FLAG1"],
            created_at=datetime.now(UTC),
            status=ApprovalStatus.PENDING,
        )
        approvals.add_pending(approval)

        app = create_control_room_app(event_bus=bus, approvals=approvals, token=token)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/approvals/test_008", params={"token": token})
            assert response.status_code == 200

            data = response.json()
            assert data["approval_id"] == "test_008"
            assert data["restored_arguments"] == {"real": "value"}
            assert data["cloaked_arguments"] == {"real": "[PERSON_1]"}
            assert "FLAG1" in data["risk_flags"]


class TestHelpers:
    """Test helper functions."""

    def test_generate_token(self) -> None:
        token1 = generate_token()
        token2 = generate_token()

        assert len(token1) >= 20  # URL-safe base64 token
        assert len(token2) >= 20
        assert token1 != token2  # Should be unique

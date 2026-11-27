"""Standalone preview script for Control Room UI with mocked events.

Run this to see the Control Room UI without waiting for Dev B's gateway integration.

Usage:
    uv run python -m cloakroom.controlroom.dev_preview
"""

import asyncio
import uuid
from datetime import UTC, datetime

import uvicorn

from cloakroom.contracts import (
    ApprovalRequest,
    ApprovalStatus,
    CatalogMetrics,
    CloakedEntity,
    EffectClass,
    GatewayEvent,
)
from cloakroom.controlroom.app import create_control_room_app, generate_token
from cloakroom.controlroom.approvals import ApprovalResolver
from cloakroom.controlroom.eventbus import EventBus


async def mock_event_publisher(event_bus: EventBus, approvals: ApprovalResolver) -> None:
    """Publish mocked gateway events for UI preview."""
    await asyncio.sleep(2)  # Let UI load first

    # Event 1: Tool discovery
    discovery_event = GatewayEvent(
        event_id=str(uuid.uuid4()),
        event_type="discovery",
        timestamp=datetime.now(UTC),
        catalog_metrics=CatalogMetrics(
            exposed_tools=6,
            total_tools=41,
            exposed_tokens_approx=2400,
            total_tokens_approx=16500,
        ),
    )
    await event_bus.publish(discovery_event)
    await asyncio.sleep(1)

    # Event 2: Read document (cloaked)
    read_event = GatewayEvent(
        event_id=str(uuid.uuid4()),
        event_type="tool_call",
        timestamp=datetime.now(UTC),
        tool_id="documents.read_text",
        effect=EffectClass.READ,
        cloud_view={
            "content": "Patient: [PERSON_1]  UHID: [MED_ID_1]\nHospital: [ORG_1]\nTotal: Rs 48,500"
        },
        entities=[
            CloakedEntity(
                placeholder="[PERSON_1]",
                entity_type="PERSON",
                tier="contextual",
                stage="gazetteer",
            ),
            CloakedEntity(
                placeholder="[MED_ID_1]",
                entity_type="MED_ID",
                tier="identifier",
                stage="detector",
            ),
            CloakedEntity(
                placeholder="[ORG_1]", entity_type="ORG", tier="contextual", stage="gazetteer"
            ),
        ],
        latency_ms=45.3,
        tripwire_passed=True,
    )
    await event_bus.publish(read_event)
    await asyncio.sleep(2)

    # Event 3: Bank query (cloaked)
    bank_event = GatewayEvent(
        event_id=str(uuid.uuid4()),
        event_type="tool_call",
        timestamp=datetime.now(UTC),
        tool_id="bank.query_transactions",
        effect=EffectClass.READ,
        cloud_view={
            "transactions": [
                {"date": "2024-01-15", "payee": "[ORG_1]", "amount": 52000, "account": "[ACCT_1]"}
            ]
        },
        entities=[
            CloakedEntity(
                placeholder="[ACCT_1]", entity_type="ACCT", tier="identifier", stage="gazetteer"
            ),
        ],
        latency_ms=28.1,
        tripwire_passed=True,
    )
    await event_bus.publish(bank_event)
    await asyncio.sleep(2)

    # Event 4: Create approval request
    approval = ApprovalRequest(
        approval_id="ap_0001",
        tool_id="mail_drafts.send_draft",
        effect=EffectClass.EXTERNAL,
        payload_hash="a7b3c9d2e5f8",
        restored_arguments={
            "to": "billing@lakeview.example",
            "subject": "Billing discrepancy for Aarav Sharma",
            "body": "Dear Lakeview Hospital billing team, the bill shows Rs 48,500 but account was charged Rs 52,000.",
        },
        cloaked_arguments={
            "to": "[EMAIL_1]",
            "subject": "Billing discrepancy for [PERSON_1]",
            "body": "Dear [ORG_1] billing team, the bill shows Rs 48,500 but account was charged Rs 52,000.",
        },
        risk_flags=["IDENTIFIER_EXPOSURE: MED_ID_1", "UNKNOWN_RECIPIENT"],
        created_at=datetime.now(UTC),
        status=ApprovalStatus.PENDING,
    )
    approvals.add_pending(approval)

    approval_event = GatewayEvent(
        event_id=str(uuid.uuid4()),
        event_type="approval_requested",
        timestamp=datetime.now(UTC),
        tool_id="mail_drafts.send_draft",
        effect=EffectClass.EXTERNAL,
        approval=approval,
        latency_ms=12.4,
    )
    await event_bus.publish(approval_event)

    # Keep publishing periodic keepalive events
    while True:
        await asyncio.sleep(30)


def main() -> None:
    """Run dev preview server."""
    print("\n" + "=" * 60)
    print("Cloakroom Control Room - Dev Preview")
    print("=" * 60)

    # Create event bus and approvals
    event_bus = EventBus()
    approvals = ApprovalResolver()

    # Generate token
    token = generate_token()
    print(f"\nAccess token: {token}")

    # Create app
    app = create_control_room_app(event_bus=event_bus, approvals=approvals, token=token)

    # Print access URL
    port = 8765
    print("\nControl Room URL:")
    print(f"  http://127.0.0.1:{port}/?token={token}")
    print("\nPress Ctrl+C to stop\n")

    # Start mock event publisher in background using lifespan context
    @app.on_event("startup")
    async def startup_event() -> None:
        _task = asyncio.create_task(mock_event_publisher(event_bus, approvals))  # noqa: RUF006
        # Keep reference to avoid garbage collection

    # Run with uvicorn
    # CRITICAL: Configure uvicorn to never write to stdout
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,  # Disable access logs
    )


if __name__ == "__main__":
    main()

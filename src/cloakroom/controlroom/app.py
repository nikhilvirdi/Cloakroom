"""FastAPI Control Room application with SSE events and approval endpoints."""

import asyncio
import json
import secrets
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from cloakroom.controlroom.approvals import ApprovalResolver
from cloakroom.controlroom.eventbus import EventBus
from cloakroom.controlroom.ui import CONTROL_ROOM_HTML


class ApprovalDecision(BaseModel):
    """Request body for approval decision."""

    approved: bool
    payload_hash: str


def create_control_room_app(
    *,
    event_bus: EventBus,
    approvals: ApprovalResolver,
    token: str,
) -> FastAPI:
    """Create FastAPI Control Room application.

    Args:
        event_bus: Event bus for subscribing to gateway events
        approvals: Approval resolver for handling decisions
        token: Per-launch authentication token

    Returns:
        Configured FastAPI application
    """
    app = FastAPI(title="Cloakroom Control Room", docs_url=None, redoc_url=None)

    def verify_token(request: Request) -> None:
        """Verify authentication token from query param or header."""
        token_from_query = request.query_params.get("token")
        token_from_header = request.headers.get("Authorization", "").replace("Bearer ", "")

        if token_from_query != token and token_from_header != token:
            raise HTTPException(status_code=403, detail="Invalid token")

    @app.get("/", response_class=HTMLResponse)
    async def serve_ui(request: Request) -> str:
        """Serve single-file Control Room UI."""
        verify_token(request)
        # Inject token into HTML for client-side use
        html = CONTROL_ROOM_HTML.replace("{{TOKEN}}", token)
        return html

    @app.get("/api/events")
    async def stream_events(request: Request) -> StreamingResponse:
        """Server-Sent Events endpoint for live event stream."""
        verify_token(request)

        async def event_generator() -> Any:
            """Generate SSE events from event bus."""
            queue = event_bus.subscribe()
            try:
                while True:
                    # Wait for next event with timeout to allow checking for client disconnect
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=30.0)
                        # Format as SSE
                        event_data = {
                            "event_id": event.event_id,
                            "event_type": event.event_type,
                            "timestamp": event.timestamp.isoformat(),
                            "tool_id": event.tool_id,
                            "effect": event.effect.value if event.effect else None,
                            "cloud_view": event.cloud_view,
                            "entities": [
                                {
                                    "placeholder": e.placeholder,
                                    "entity_type": e.entity_type,
                                    "tier": e.tier,
                                    "stage": e.stage,
                                }
                                for e in event.entities
                            ],
                            "latency_ms": event.latency_ms,
                            "tripwire_passed": event.tripwire_passed,
                            "decision": event.decision,
                            "catalog_metrics": (
                                {
                                    "exposed_tools": event.catalog_metrics.exposed_tools,
                                    "total_tools": event.catalog_metrics.total_tools,
                                    "exposed_tokens_approx": event.catalog_metrics.exposed_tokens_approx,
                                    "total_tokens_approx": event.catalog_metrics.total_tokens_approx,
                                }
                                if event.catalog_metrics
                                else None
                            ),
                        }
                        yield f"data: {json.dumps(event_data)}\n\n"
                    except TimeoutError:
                        # Send keepalive
                        yield ": keepalive\n\n"

            except asyncio.CancelledError:
                pass
            finally:
                event_bus.unsubscribe(queue)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/api/state")
    async def get_state(request: Request) -> dict[str, Any]:
        """Get current Control Room state (history and pending approvals)."""
        verify_token(request)

        history = event_bus.get_history()
        pending = approvals.list_pending()

        return {
            "history": [
                {
                    "event_id": e.event_id,
                    "event_type": e.event_type,
                    "timestamp": e.timestamp.isoformat(),
                    "tool_id": e.tool_id,
                    "effect": e.effect.value if e.effect else None,
                    "entity_count": len(e.entities),
                    "latency_ms": e.latency_ms,
                }
                for e in history[-100:]  # Last 100 events
            ],
            "pending_approvals": [
                {
                    "approval_id": a.approval_id,
                    "tool_id": a.tool_id,
                    "effect": a.effect.value,
                    "payload_hash": a.payload_hash,
                    "risk_flags": a.risk_flags,
                    "created_at": a.created_at.isoformat(),
                    "status": a.status.value,
                    # Note: Real payload shown to user but not sent over wire initially
                }
                for a in pending
            ],
        }

    @app.post("/api/approvals/{approval_id}/decision")
    async def make_decision(
        approval_id: str, decision: ApprovalDecision, request: Request
    ) -> dict[str, Any]:
        """Make approval decision (approve or deny)."""
        verify_token(request)

        try:
            updated = await approvals.resolve(
                approval_id, approved=decision.approved, payload_hash=decision.payload_hash
            )
            return {
                "approval_id": updated.approval_id,
                "status": updated.status.value,
                "tool_id": updated.tool_id,
            }
        except Exception as e:
            raise HTTPException(
                status_code=404, detail="Approval not found or hash mismatch"
            ) from e

    @app.get("/api/approvals/{approval_id}")
    async def get_approval_details(approval_id: str, request: Request) -> dict[str, Any]:
        """Get full approval details including restored payload."""
        verify_token(request)

        approval = approvals.get_approval(approval_id)
        if not approval:
            raise HTTPException(status_code=404, detail="Approval not found")

        return {
            "approval_id": approval.approval_id,
            "tool_id": approval.tool_id,
            "effect": approval.effect.value,
            "restored_arguments": approval.restored_arguments,
            "cloaked_arguments": approval.cloaked_arguments,
            "risk_flags": approval.risk_flags,
            "payload_hash": approval.payload_hash,
            "created_at": approval.created_at.isoformat(),
            "status": approval.status.value,
        }

    return app


def generate_token() -> str:
    """Generate a secure random token for Control Room access.

    Returns:
        URL-safe base64 token (24 characters)
    """
    return secrets.token_urlsafe(24)

"""Test doubles for Dev A's modules (vault, cloak, control room).

These are temporary stubs used until Dev A's implementation is merged.
"""

from __future__ import annotations

from typing import Any

from cloakroom.contracts import (
    CloakEngineProtocol,
    CloakResult,
    EventBusProtocol,
    GatewayEvent,
    RestoreResult,
)


class DummyCloakEngine(CloakEngineProtocol):
    """Test double for cloak engine - passthrough implementation."""

    def cloak(self, payload: Any, *, server_id: str = "", tool_name: str = "") -> CloakResult:
        """Passthrough cloak - returns payload unchanged.

        Args:
            payload: Payload to cloak
            server_id: Server identifier
            tool_name: Tool name

        Returns:
            CloakResult with unchanged payload
        """
        return CloakResult(
            cloaked_payload=payload,
            raw_payload=payload,
            entities=[],
            tripwire_passed=True,
            withheld=False,
            withhold_reason=None,
            latency_ms=0.0,
        )

    def restore(self, arguments: dict[str, Any]) -> RestoreResult:
        """Passthrough restore - returns arguments unchanged.

        Args:
            arguments: Arguments to restore

        Returns:
            RestoreResult with unchanged arguments
        """
        # Check for invented placeholders (simple pattern matching)
        blocked = False
        unknown_placeholders = []

        # Simple check for placeholder patterns in string values
        for _key, value in arguments.items():
            if isinstance(value, str) and "[" in value and "]" in value:
                # Extract placeholder patterns
                import re

                placeholders = re.findall(r"\[([A-Z_]+)_\d+\]", value)
                for placeholder in placeholders:
                    # Check if it's a known type
                    known_types = {
                        "PERSON",
                        "EMAIL",
                        "ACCT",
                        "MED_ID",
                        "ORG",
                        "PHONE",
                        "GOVID",
                        "ADDR",
                        "SECRET",
                    }
                    if placeholder not in known_types:
                        blocked = True
                        unknown_placeholders.append(f"[{placeholder}_X]")

        return RestoreResult(
            restored_arguments=arguments,
            used_placeholders=[],
            contains_identifier_tier=False,
            blocked=blocked,
            unknown_placeholders=unknown_placeholders,
        )

    def list_vault_summary(self) -> list[dict[str, Any]]:
        """Return empty vault summary.

        Returns:
            Empty list
        """
        return []


class DummyEventBus(EventBusProtocol):
    """Test double for event bus - stores events in memory."""

    def __init__(self) -> None:
        """Initialize event bus."""
        self._history: list[GatewayEvent] = []

    async def publish(self, event: GatewayEvent) -> None:
        """Publish an event.

        Args:
            event: Gateway event
        """
        self._history.append(event)

    def get_history(self) -> list[GatewayEvent]:
        """Get event history.

        Returns:
            List of published events
        """
        return self._history.copy()

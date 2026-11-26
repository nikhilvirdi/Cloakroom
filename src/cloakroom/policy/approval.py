"""Approval manager for external and unknown effect tools."""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from cloakroom.contracts import ApprovalRequest, ApprovalStatus, EffectClass


class ApprovalManager:
    """Manages approval requests for external/unknown tools.

    Implements ApprovalResolverProtocol from contracts.
    """

    def __init__(
        self,
        wait_timeout: float = 30.0,
        approval_expiry: float = 120.0,
        known_contacts: set[str] | None = None,
    ) -> None:
        """Initialize approval manager.

        Args:
            wait_timeout: Seconds to wait for approval before returning pending (default 30s)
            approval_expiry: Seconds before approval expires if not answered (default 120s)
            known_contacts: Set of known contact emails for recipient validation
        """
        self._wait_timeout = wait_timeout
        self._approval_expiry = approval_expiry
        self._known_contacts = known_contacts or set()

        # Active approvals: approval_id -> (request, event, expiry_time)
        self._approvals: dict[str, tuple[ApprovalRequest, asyncio.Event, float]] = {}

        # Counter for generating approval IDs
        self._counter = 0

    def _generate_approval_id(self) -> str:
        """Generate a unique approval ID."""
        self._counter += 1
        return f"ap_{self._counter:04d}"

    def _compute_payload_hash(self, tool_id: str, arguments: dict[str, Any]) -> str:
        """Compute canonical SHA-256 hash of tool invocation.

        Args:
            tool_id: Tool identifier
            arguments: Restored arguments

        Returns:
            SHA-256 hash as hex string
        """
        # Canonical representation: JSON with sorted keys
        canonical = json.dumps({"tool_id": tool_id, "arguments": arguments}, sort_keys=True)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _check_risk_flags(
        self,
        tool_id: str,
        arguments: dict[str, Any],
        contains_identifier_tier: bool,
        identifier_placeholders: list[str],
    ) -> list[str]:
        """Identify risk flags for an approval request.

        Args:
            tool_id: Tool identifier
            arguments: Restored arguments (may contain emails, recipients)
            contains_identifier_tier: Whether identifier-tier data is present
            identifier_placeholders: List of identifier placeholders being restored

        Returns:
            List of risk flag strings
        """
        flags = []

        # Check for unknown recipients
        # Look for common email/recipient fields
        for key in ["to", "recipient", "email", "recipients"]:
            if key in arguments:
                recipient = arguments[key]
                if (
                    isinstance(recipient, str)
                    and "@" in recipient
                    and recipient not in self._known_contacts
                ):
                    flags.append("UNKNOWN_RECIPIENT")
                    break

        # Check for identifier exposure
        if contains_identifier_tier and identifier_placeholders:
            exposed = ", ".join(identifier_placeholders)
            flags.append(f"IDENTIFIER_EXPOSURE: {exposed}")

        return flags

    async def request_approval(
        self,
        tool_id: str,
        effect: EffectClass,
        restored_arguments: dict[str, Any],
        cloaked_arguments: dict[str, Any],
        contains_identifier_tier: bool = False,
        identifier_placeholders: list[str] | None = None,
    ) -> tuple[ApprovalRequest, bool]:
        """Request approval for a tool invocation.

        This method waits up to `wait_timeout` seconds for a decision.
        If no decision arrives, it returns the approval as PENDING.

        Args:
            tool_id: Tool identifier
            effect: Effect classification
            restored_arguments: Arguments with real values restored
            cloaked_arguments: Arguments with placeholders (for display)
            contains_identifier_tier: Whether identifier-tier data is involved
            identifier_placeholders: List of identifier placeholder tokens

        Returns:
            Tuple of (ApprovalRequest, decision_received)
            - decision_received is True if approved/denied during wait, False if pending
        """
        approval_id = self._generate_approval_id()
        payload_hash = self._compute_payload_hash(tool_id, restored_arguments)

        risk_flags = self._check_risk_flags(
            tool_id,
            restored_arguments,
            contains_identifier_tier,
            identifier_placeholders or [],
        )

        # Create approval request
        request = ApprovalRequest(
            approval_id=approval_id,
            tool_id=tool_id,
            effect=effect,
            payload_hash=payload_hash,
            restored_arguments=restored_arguments,
            cloaked_arguments=cloaked_arguments,
            risk_flags=risk_flags,
            created_at=datetime.now(UTC),
            status=ApprovalStatus.PENDING,
        )

        # Create event for waiting on decision
        event = asyncio.Event()
        expiry_time = datetime.now(UTC).timestamp() + self._approval_expiry

        # Store approval
        self._approvals[approval_id] = (request, event, expiry_time)

        # Wait for decision (with timeout)
        try:
            await asyncio.wait_for(event.wait(), timeout=self._wait_timeout)
            # Decision received within wait timeout
            updated_request, _, _ = self._approvals[approval_id]
            return updated_request, True
        except TimeoutError:
            # No decision within wait timeout - return pending
            return request, False

    async def resolve(
        self, approval_id: str, *, approved: bool, payload_hash: str
    ) -> ApprovalRequest:
        """Resolve an approval request.

        Implements ApprovalResolverProtocol.resolve().

        Args:
            approval_id: Approval identifier
            approved: Whether the action is approved
            payload_hash: Hash of the payload being approved (must match)

        Returns:
            Updated approval request

        Raises:
            ValueError: If approval not found, hash mismatch, or already resolved
        """
        if approval_id not in self._approvals:
            raise ValueError(f"Approval not found: {approval_id}")

        request, event, expiry_time = self._approvals[approval_id]

        # Check if already resolved
        if request.status != ApprovalStatus.PENDING:
            raise ValueError(f"Approval already resolved: {approval_id}")

        # Check expiry
        if datetime.now(UTC).timestamp() > expiry_time:
            # Mark as expired and deny
            updated = ApprovalRequest(
                approval_id=request.approval_id,
                tool_id=request.tool_id,
                effect=request.effect,
                payload_hash=request.payload_hash,
                restored_arguments=request.restored_arguments,
                cloaked_arguments=request.cloaked_arguments,
                risk_flags=request.risk_flags,
                created_at=request.created_at,
                status=ApprovalStatus.EXPIRED,
            )
            self._approvals[approval_id] = (updated, event, expiry_time)
            event.set()
            raise ValueError(f"Approval expired: {approval_id}")

        # Verify payload hash
        if payload_hash != request.payload_hash:
            # Hash mismatch - deny
            updated = ApprovalRequest(
                approval_id=request.approval_id,
                tool_id=request.tool_id,
                effect=request.effect,
                payload_hash=request.payload_hash,
                restored_arguments=request.restored_arguments,
                cloaked_arguments=request.cloaked_arguments,
                risk_flags=request.risk_flags,
                created_at=request.created_at,
                status=ApprovalStatus.DENIED,
            )
            self._approvals[approval_id] = (updated, event, expiry_time)
            event.set()
            raise ValueError(f"Payload hash mismatch for approval: {approval_id}")

        # Update status
        new_status = ApprovalStatus.APPROVED if approved else ApprovalStatus.DENIED
        updated = ApprovalRequest(
            approval_id=request.approval_id,
            tool_id=request.tool_id,
            effect=request.effect,
            payload_hash=request.payload_hash,
            restored_arguments=request.restored_arguments,
            cloaked_arguments=request.cloaked_arguments,
            risk_flags=request.risk_flags,
            created_at=request.created_at,
            status=new_status,
        )

        # Update stored request and signal event
        self._approvals[approval_id] = (updated, event, expiry_time)
        event.set()

        return updated

    def list_pending(self) -> list[ApprovalRequest]:
        """List all pending approval requests.

        Implements ApprovalResolverProtocol.list_pending().

        Returns:
            List of pending approval requests
        """
        pending = []
        current_time = datetime.now(UTC).timestamp()

        for approval_id, (request, event, expiry_time) in list(self._approvals.items()):
            # Check if expired
            if request.status == ApprovalStatus.PENDING and current_time > expiry_time:
                # Mark as expired
                expired = ApprovalRequest(
                    approval_id=request.approval_id,
                    tool_id=request.tool_id,
                    effect=request.effect,
                    payload_hash=request.payload_hash,
                    restored_arguments=request.restored_arguments,
                    cloaked_arguments=request.cloaked_arguments,
                    risk_flags=request.risk_flags,
                    created_at=request.created_at,
                    status=ApprovalStatus.EXPIRED,
                )
                self._approvals[approval_id] = (expired, event, expiry_time)
                event.set()
            elif request.status == ApprovalStatus.PENDING:
                pending.append(request)

        return pending

    def get_approval(self, approval_id: str) -> ApprovalRequest | None:
        """Get an approval request by ID.

        Args:
            approval_id: Approval identifier

        Returns:
            Approval request or None if not found
        """
        if approval_id in self._approvals:
            request, _, _ = self._approvals[approval_id]
            return request
        return None

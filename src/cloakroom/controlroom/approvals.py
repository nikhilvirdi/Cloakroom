"""Simple approval resolver for Control Room (Dev A's part of approval flow)."""

from cloakroom.contracts import ApprovalRequest, ApprovalStatus
from cloakroom.errors import PolicyError


class ApprovalResolver:
    """Simple in-memory approval resolver for MVP."""

    def __init__(self) -> None:
        """Initialize approval resolver."""
        self._pending: dict[str, ApprovalRequest] = {}

    def add_pending(self, approval: ApprovalRequest) -> None:
        """Add a pending approval request.

        Args:
            approval: Approval request to add
        """
        self._pending[approval.approval_id] = approval

    async def resolve(
        self, approval_id: str, *, approved: bool, payload_hash: str
    ) -> ApprovalRequest:
        """Resolve an approval (approve or deny).

        Args:
            approval_id: Approval identifier
            approved: True to approve, False to deny
            payload_hash: Hash of payload being approved (must match)

        Returns:
            Updated approval request

        Raises:
            PolicyError: If approval not found or hash mismatch
        """
        if approval_id not in self._pending:
            raise PolicyError()

        approval = self._pending[approval_id]

        # Verify hash matches
        if approval.payload_hash != payload_hash:
            raise PolicyError()

        # Update status
        new_status = ApprovalStatus.APPROVED if approved else ApprovalStatus.DENIED
        # Note: ApprovalRequest is frozen, so we'd need to create a new one
        # For MVP, we'll just update in place (not ideal but works)
        # In production, use a mutable model or dataclass with replace()
        updated = ApprovalRequest(
            approval_id=approval.approval_id,
            tool_id=approval.tool_id,
            effect=approval.effect,
            payload_hash=approval.payload_hash,
            restored_arguments=approval.restored_arguments,
            cloaked_arguments=approval.cloaked_arguments,
            risk_flags=approval.risk_flags,
            created_at=approval.created_at,
            status=new_status,
        )

        # Remove from pending if resolved
        if new_status in (ApprovalStatus.APPROVED, ApprovalStatus.DENIED):
            del self._pending[approval_id]

        return updated

    def list_pending(self) -> list[ApprovalRequest]:
        """List all pending approval requests.

        Returns:
            List of pending approvals
        """
        return list(self._pending.values())

    def get_approval(self, approval_id: str) -> ApprovalRequest | None:
        """Get approval by ID.

        Args:
            approval_id: Approval identifier

        Returns:
            Approval request or None if not found
        """
        return self._pending.get(approval_id)

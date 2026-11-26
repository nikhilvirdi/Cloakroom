"""Tests for policy engine: effect classification and approval management."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime

import pytest

from cloakroom.contracts import ApprovalStatus, EffectClass
from cloakroom.policy.approval import ApprovalManager
from cloakroom.policy.effects import classify_effect


class TestEffectClassification:
    """Test effect classification priority order."""

    def test_config_override_takes_priority(self) -> None:
        """Config overrides beat all other hints."""
        # Even with read-only hint, config override wins
        config = {"server.tool": EffectClass.EXTERNAL}
        annotations = {"readOnlyHint": True}

        result = classify_effect("server.tool", annotations, config)
        assert result == EffectClass.EXTERNAL

    def test_read_only_hint_gives_read(self) -> None:
        """readOnlyHint → READ."""
        annotations = {"readOnlyHint": True}
        result = classify_effect("server.tool", annotations)
        assert result == EffectClass.READ

    def test_destructive_hint_alone_gives_local_write(self) -> None:
        """destructiveHint without openWorld → LOCAL_WRITE."""
        annotations = {"destructiveHint": True}
        result = classify_effect("server.tool", annotations)
        assert result == EffectClass.LOCAL_WRITE

    def test_destructive_and_open_world_gives_external(self) -> None:
        """destructiveHint + openWorldHint → EXTERNAL."""
        annotations = {"destructiveHint": True, "openWorldHint": True}
        result = classify_effect("server.tool", annotations)
        assert result == EffectClass.EXTERNAL

    def test_open_world_hint_alone_gives_external(self) -> None:
        """openWorldHint alone → EXTERNAL."""
        annotations = {"openWorldHint": True}
        result = classify_effect("server.tool", annotations)
        assert result == EffectClass.EXTERNAL

    def test_no_annotations_defaults_to_unknown(self) -> None:
        """No annotations → UNKNOWN (fail-safe)."""
        result = classify_effect("server.tool")
        assert result == EffectClass.UNKNOWN

    def test_empty_annotations_defaults_to_unknown(self) -> None:
        """Empty annotations dict → UNKNOWN."""
        result = classify_effect("server.tool", {})
        assert result == EffectClass.UNKNOWN

    def test_priority_order(self) -> None:
        """Verify complete priority order: config > annotations > default."""
        config = {"server.tool": EffectClass.LOCAL_WRITE}
        annotations = {"readOnlyHint": True}

        # With config: config wins
        assert classify_effect("server.tool", annotations, config) == EffectClass.LOCAL_WRITE

        # Without config: annotations win
        assert classify_effect("server.tool", annotations) == EffectClass.READ

        # Without either: default to UNKNOWN
        assert classify_effect("server.tool") == EffectClass.UNKNOWN


class TestApprovalManager:
    """Test approval manager for external/unknown tools."""

    @pytest.fixture
    def manager(self) -> ApprovalManager:
        """Create approval manager with known contacts."""
        return ApprovalManager(
            wait_timeout=0.1,  # Fast timeout for tests
            approval_expiry=1.0,  # Short expiry for tests
            known_contacts={"billing@lakeview.example", "aarav.sharma@example.com"},
        )

    def test_approval_id_generation(self, manager: ApprovalManager) -> None:
        """Approval IDs are unique and sequential."""
        id1 = manager._generate_approval_id()
        id2 = manager._generate_approval_id()
        assert id1.startswith("ap_")
        assert id2.startswith("ap_")
        assert id1 != id2

    def test_payload_hash_computation(self, manager: ApprovalManager) -> None:
        """Canonical payload hashing is consistent."""
        args1 = {"to": "test@example.com", "subject": "Hello"}
        args2 = {"subject": "Hello", "to": "test@example.com"}  # Different order

        hash1 = manager._compute_payload_hash("mail.send", args1)
        hash2 = manager._compute_payload_hash("mail.send", args2)

        # Should be identical (canonical JSON with sorted keys)
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex

    def test_different_payloads_different_hashes(self, manager: ApprovalManager) -> None:
        """Different payloads produce different hashes."""
        args1 = {"to": "test@example.com", "subject": "Hello"}
        args2 = {"to": "other@example.com", "subject": "Hello"}

        hash1 = manager._compute_payload_hash("mail.send", args1)
        hash2 = manager._compute_payload_hash("mail.send", args2)

        assert hash1 != hash2

    def test_unknown_recipient_flag(self, manager: ApprovalManager) -> None:
        """Unknown recipient triggers risk flag."""
        # Known recipient - no flag
        args_known = {"to": "billing@lakeview.example", "body": "test"}
        flags_known = manager._check_risk_flags("mail.send", args_known, False, [])
        assert "UNKNOWN_RECIPIENT" not in flags_known

        # Unknown recipient - flag raised
        args_unknown = {"to": "verify-refund@external-audit.example", "body": "test"}
        flags_unknown = manager._check_risk_flags("mail.send", args_unknown, False, [])
        assert "UNKNOWN_RECIPIENT" in flags_unknown

    def test_identifier_exposure_flag(self, manager: ApprovalManager) -> None:
        """Identifier tier exposure triggers risk flag."""
        args = {"account": "[ACCT_1]", "name": "[PERSON_1]"}
        flags = manager._check_risk_flags(
            "bank.transfer",
            args,
            contains_identifier_tier=True,
            identifier_placeholders=["[ACCT_1]", "[PERSON_1]"],
        )

        # Should have identifier exposure flag with placeholders listed
        exposure_flags = [f for f in flags if f.startswith("IDENTIFIER_EXPOSURE")]
        assert len(exposure_flags) == 1
        assert "[ACCT_1]" in exposure_flags[0]
        assert "[PERSON_1]" in exposure_flags[0]

    def test_multiple_risk_flags(self, manager: ApprovalManager) -> None:
        """Multiple risk flags can be raised together."""
        args = {"to": "unknown@bad.example", "account": "[ACCT_1]"}
        flags = manager._check_risk_flags(
            "mail.send",
            args,
            contains_identifier_tier=True,
            identifier_placeholders=["[ACCT_1]"],
        )

        assert "UNKNOWN_RECIPIENT" in flags
        assert any(f.startswith("IDENTIFIER_EXPOSURE") for f in flags)

    @pytest.mark.asyncio
    async def test_request_approval_basic(self, manager: ApprovalManager) -> None:
        """Basic approval request creation and pending status."""
        args = {"to": "test@example.com", "body": "Hello"}

        # Request approval (will timeout waiting for decision)
        request, decision_received = await manager.request_approval(
            tool_id="mail.send",
            effect=EffectClass.EXTERNAL,
            restored_arguments=args,
            cloaked_arguments=args,
        )

        # Should timeout and return pending
        assert not decision_received
        assert request.status == ApprovalStatus.PENDING
        assert request.tool_id == "mail.send"
        assert request.effect == EffectClass.EXTERNAL
        assert request.approval_id.startswith("ap_")
        assert len(request.payload_hash) == 64

    @pytest.mark.asyncio
    async def test_approval_resolved_approved(self, manager: ApprovalManager) -> None:
        """Approval can be resolved as approved."""
        args = {"to": "test@example.com", "body": "Hello"}

        # Start approval request in background
        async def request_approval_task() -> tuple:
            return await manager.request_approval(
                tool_id="mail.send",
                effect=EffectClass.EXTERNAL,
                restored_arguments=args,
                cloaked_arguments=args,
            )

        # Create task
        task = asyncio.create_task(request_approval_task())

        # Give it a moment to start
        await asyncio.sleep(0.01)

        # Get the pending approval
        pending = manager.list_pending()
        assert len(pending) == 1
        approval_id = pending[0].approval_id
        payload_hash = pending[0].payload_hash

        # Approve it
        resolved = await manager.resolve(approval_id, approved=True, payload_hash=payload_hash)
        assert resolved.status == ApprovalStatus.APPROVED

        # Task should complete with approval
        request, decision_received = await task
        assert decision_received
        assert request.status == ApprovalStatus.APPROVED

    @pytest.mark.asyncio
    async def test_approval_resolved_denied(self, manager: ApprovalManager) -> None:
        """Approval can be resolved as denied."""
        args = {"to": "test@example.com", "body": "Hello"}

        # Start approval request in background
        approval_task = asyncio.create_task(
            manager.request_approval(
                tool_id="mail.send",
                effect=EffectClass.EXTERNAL,
                restored_arguments=args,
                cloaked_arguments=args,
            )
        )

        await asyncio.sleep(0.01)

        # Deny it
        pending = manager.list_pending()
        approval_id = pending[0].approval_id
        payload_hash = pending[0].payload_hash

        resolved = await manager.resolve(approval_id, approved=False, payload_hash=payload_hash)
        assert resolved.status == ApprovalStatus.DENIED

        # Task should complete with denial
        request, decision_received = await approval_task
        assert decision_received
        assert request.status == ApprovalStatus.DENIED

    @pytest.mark.asyncio
    async def test_payload_hash_mismatch_denies(self, manager: ApprovalManager) -> None:
        """Payload hash mismatch results in denial."""
        args = {"to": "test@example.com", "body": "Hello"}

        hash_task = asyncio.create_task(
            manager.request_approval(
                tool_id="mail.send",
                effect=EffectClass.EXTERNAL,
                restored_arguments=args,
                cloaked_arguments=args,
            )
        )

        await asyncio.sleep(0.01)

        pending = manager.list_pending()
        approval_id = pending[0].approval_id

        # Try to resolve with wrong hash
        with pytest.raises(ValueError, match="Payload hash mismatch"):
            await manager.resolve(approval_id, approved=True, payload_hash="wrong_hash")

        # Approval should be denied due to hash mismatch
        updated = manager.get_approval(approval_id)
        assert updated is not None
        assert updated.status == ApprovalStatus.DENIED

        # Clean up background task
        hash_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await hash_task

    @pytest.mark.asyncio
    async def test_approval_not_found_error(self, manager: ApprovalManager) -> None:
        """Resolving unknown approval raises error."""
        with pytest.raises(ValueError, match="Approval not found"):
            await manager.resolve("ap_9999", approved=True, payload_hash="hash")

    @pytest.mark.asyncio
    async def test_already_resolved_error(self, manager: ApprovalManager) -> None:
        """Resolving already-resolved approval raises error."""
        args = {"to": "test@example.com", "body": "Hello"}

        task = asyncio.create_task(
            manager.request_approval(
                tool_id="mail.send",
                effect=EffectClass.EXTERNAL,
                restored_arguments=args,
                cloaked_arguments=args,
            )
        )

        await asyncio.sleep(0.01)

        pending = manager.list_pending()
        approval_id = pending[0].approval_id
        payload_hash = pending[0].payload_hash

        # Resolve once
        await manager.resolve(approval_id, approved=True, payload_hash=payload_hash)
        await task

        # Try to resolve again
        with pytest.raises(ValueError, match="already resolved"):
            await manager.resolve(approval_id, approved=False, payload_hash=payload_hash)

    @pytest.mark.asyncio
    async def test_approval_expiry(self, manager: ApprovalManager) -> None:
        """Approvals expire after expiry timeout."""
        args = {"to": "test@example.com", "body": "Hello"}

        # Create approval (expires in 1s based on fixture)
        request, _ = await manager.request_approval(
            tool_id="mail.send",
            effect=EffectClass.EXTERNAL,
            restored_arguments=args,
            cloaked_arguments=args,
        )

        approval_id = request.approval_id
        payload_hash = request.payload_hash

        # Wait for expiry
        await asyncio.sleep(1.1)

        # Try to resolve expired approval
        with pytest.raises(ValueError, match="expired"):
            await manager.resolve(approval_id, approved=True, payload_hash=payload_hash)

        # Should be marked as expired
        updated = manager.get_approval(approval_id)
        assert updated is not None
        assert updated.status == ApprovalStatus.EXPIRED

    @pytest.mark.asyncio
    async def test_list_pending_excludes_expired(self, manager: ApprovalManager) -> None:
        """list_pending() auto-expires and excludes expired approvals."""
        args = {"to": "test@example.com", "body": "Hello"}

        # Create approval
        await manager.request_approval(
            tool_id="mail.send",
            effect=EffectClass.EXTERNAL,
            restored_arguments=args,
            cloaked_arguments=args,
        )

        # Should be pending initially
        pending = manager.list_pending()
        assert len(pending) == 1

        # Wait for expiry
        await asyncio.sleep(1.1)

        # list_pending should auto-expire and return empty
        pending = manager.list_pending()
        assert len(pending) == 0

    @pytest.mark.asyncio
    async def test_approval_wait_timeout_separate_from_expiry(
        self, manager: ApprovalManager
    ) -> None:
        """Wait timeout (30s default, 0.1s in tests) is separate from expiry (120s default, 1s in tests)."""
        args = {"to": "test@example.com", "body": "Hello"}

        # Request approval - will wait 0.1s, timeout, return pending
        # but approval stays open for 1.0s expiry
        request, decision_received = await manager.request_approval(
            tool_id="mail.send",
            effect=EffectClass.EXTERNAL,
            restored_arguments=args,
            cloaked_arguments=args,
        )

        # Should timeout during wait
        assert not decision_received
        assert request.status == ApprovalStatus.PENDING

        # Approval should still be resolvable (not expired yet)
        pending = manager.list_pending()
        assert len(pending) == 1

        # Can still resolve within expiry window
        resolved = await manager.resolve(
            request.approval_id, approved=True, payload_hash=request.payload_hash
        )
        assert resolved.status == ApprovalStatus.APPROVED

    def test_get_approval(self, manager: ApprovalManager) -> None:
        """get_approval returns approval by ID."""
        # Non-existent approval
        assert manager.get_approval("ap_9999") is None

    @pytest.mark.asyncio
    async def test_restored_vs_cloaked_arguments(self, manager: ApprovalManager) -> None:
        """Approval stores both restored and cloaked arguments."""
        restored = {"to": "aarav.sharma@example.com", "body": "Contains [ACCT_1]"}
        cloaked = {"to": "[EMAIL_1]", "body": "Contains [ACCT_1]"}

        request, _ = await manager.request_approval(
            tool_id="mail.send",
            effect=EffectClass.EXTERNAL,
            restored_arguments=restored,
            cloaked_arguments=cloaked,
            contains_identifier_tier=True,
            identifier_placeholders=["[ACCT_1]"],
        )

        # Both versions should be stored
        assert request.restored_arguments == restored
        assert request.cloaked_arguments == cloaked

        # Risk flags should include identifier exposure
        assert any(f.startswith("IDENTIFIER_EXPOSURE") for f in request.risk_flags)


class TestApprovalManagerEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_multiple_concurrent_approvals(self) -> None:
        """Multiple approvals can be pending simultaneously."""
        manager = ApprovalManager(wait_timeout=0.1, approval_expiry=2.0)

        # Create multiple approval requests
        tasks = [
            manager.request_approval(
                tool_id=f"tool_{i}",
                effect=EffectClass.EXTERNAL,
                restored_arguments={"param": f"value_{i}"},
                cloaked_arguments={"param": f"value_{i}"},
            )
            for i in range(5)
        ]

        # All should timeout and be pending
        results = await asyncio.gather(*tasks)
        assert all(not received for _, received in results)

        # All should be in pending list
        pending = manager.list_pending()
        assert len(pending) == 5

    @pytest.mark.asyncio
    async def test_recipient_field_variations(self) -> None:
        """Check common recipient field names."""
        manager = ApprovalManager(known_contacts={"known@example.com"})

        # Test various field names
        test_cases = [
            ({"to": "unknown@example.com"}, True),
            ({"recipient": "unknown@example.com"}, True),
            ({"email": "unknown@example.com"}, True),
            ({"recipients": "unknown@example.com"}, True),
            ({"to": "known@example.com"}, False),
            ({"other_field": "unknown@example.com"}, False),  # Field not checked
        ]

        for args, should_flag in test_cases:
            flags = manager._check_risk_flags("tool", args, False, [])
            has_flag = "UNKNOWN_RECIPIENT" in flags
            assert has_flag == should_flag, f"Failed for {args}"

    @pytest.mark.asyncio
    async def test_no_identifier_exposure_without_flag(self) -> None:
        """Identifier exposure flag only appears when flag is True."""
        manager = ApprovalManager()

        # Has placeholders but flag is False
        flags = manager._check_risk_flags(
            "tool",
            {"data": "[PERSON_1]"},
            contains_identifier_tier=False,
            identifier_placeholders=[],
        )

        assert not any(f.startswith("IDENTIFIER_EXPOSURE") for f in flags)

    @pytest.mark.asyncio
    async def test_approval_created_at_timestamp(self) -> None:
        """Approval has valid created_at timestamp."""
        manager = ApprovalManager()
        args = {"to": "test@example.com"}
        before = datetime.now(UTC)

        request, _ = await manager.request_approval(
            tool_id="mail.send",
            effect=EffectClass.EXTERNAL,
            restored_arguments=args,
            cloaked_arguments=args,
        )

        after = datetime.now(UTC)

        # Timestamp should be between before and after
        assert before <= request.created_at <= after

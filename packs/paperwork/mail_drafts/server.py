"""Mail drafts MCP server - local draft creation and sending."""

import json
from datetime import UTC, datetime
from pathlib import Path

# Default directories
DRAFTS_DIR = Path(__file__).parent.parent.parent.parent / "demo_data" / "mail" / "drafts"
OUTBOX_DIR = Path(__file__).parent.parent.parent.parent / "demo_data" / "mail" / "outbox"

# Ensure directories exist
DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
OUTBOX_DIR.mkdir(parents=True, exist_ok=True)

# Counter for ensuring unique IDs
_draft_counter = 0


def create_draft(to: str, subject: str, body: str, cc: str = "", bcc: str = "") -> dict[str, str]:
    """Create a new email draft (local write - not sent externally).

    Args:
        to: Recipient email address. Placeholders like [EMAIL_1] are accepted.
        subject: Email subject line. Placeholders like [PERSON_1] are accepted.
        body: Email body text. Placeholders like [ACCT_1], [PERSON_1] etc. are accepted.
        cc: CC recipients (optional). Placeholders are accepted.
        bcc: BCC recipients (optional). Placeholders are accepted.

    Returns:
        Draft information including draft_id and filepath.
    """
    global _draft_counter
    # Generate draft ID from timestamp with counter to ensure uniqueness
    _draft_counter += 1
    draft_id = datetime.now(UTC).strftime(f"draft_%Y%m%d_%H%M%S_%f_{_draft_counter}")
    draft_file = DRAFTS_DIR / f"{draft_id}.json"

    draft_data = {
        "draft_id": draft_id,
        "to": to,
        "subject": subject,
        "body": body,
        "cc": cc,
        "bcc": bcc,
        "created_at": datetime.now(UTC).isoformat(),
        "status": "draft",
    }

    draft_file.write_text(json.dumps(draft_data, indent=2), encoding="utf-8")

    return {
        "draft_id": draft_id,
        "filepath": str(draft_file.relative_to(DRAFTS_DIR.parent)),
        "status": "draft_created",
    }


def list_drafts() -> list[dict[str, str]]:
    """List all email drafts.

    Returns:
        List of drafts with id, subject, and recipient information.
    """
    drafts = []

    if not DRAFTS_DIR.exists():
        return []

    for draft_file in DRAFTS_DIR.glob("*.json"):
        try:
            draft_data = json.loads(draft_file.read_text(encoding="utf-8"))
            drafts.append(
                {
                    "draft_id": draft_data.get("draft_id", ""),
                    "to": draft_data.get("to", ""),
                    "subject": draft_data.get("subject", ""),
                    "created_at": draft_data.get("created_at", ""),
                    "status": draft_data.get("status", "draft"),
                }
            )
        except (OSError, json.JSONDecodeError):
            continue

    return sorted(drafts, key=lambda d: d.get("created_at", ""), reverse=True)


def read_draft(draft_id: str) -> dict[str, str]:
    """Read the full contents of a specific draft.

    Args:
        draft_id: The draft identifier returned from create_draft or list_drafts.

    Returns:
        Complete draft information.
    """
    draft_file = DRAFTS_DIR / f"{draft_id}.json"

    if not draft_file.exists():
        raise FileNotFoundError(f"Draft not found: {draft_id}")

    try:
        draft_data = json.loads(draft_file.read_text(encoding="utf-8"))
        return draft_data
    except (OSError, json.JSONDecodeError) as e:
        raise ValueError(f"Could not read draft: {e}") from e


def send_draft(draft_id: str) -> dict[str, str]:
    """Send a draft email (writes to local outbox - external action requiring approval).

    This writes the email to the local outbox directory. It does NOT send via SMTP.
    The outbox can be inspected to verify what would have been sent.

    Args:
        draft_id: The draft identifier to send.

    Returns:
        Confirmation with outbox filepath.
    """
    draft_file = DRAFTS_DIR / f"{draft_id}.json"

    if not draft_file.exists():
        raise FileNotFoundError(f"Draft not found: {draft_id}")

    try:
        draft_data = json.loads(draft_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise ValueError(f"Could not read draft: {e}") from e

    # Mark as sent and move to outbox
    draft_data["status"] = "sent"
    draft_data["sent_at"] = datetime.now(UTC).isoformat()

    outbox_file = OUTBOX_DIR / f"sent_{draft_id}.json"
    outbox_file.write_text(json.dumps(draft_data, indent=2), encoding="utf-8")

    # Optionally remove from drafts
    # draft_file.unlink()  # Keeping draft for now for demo purposes

    return {
        "draft_id": draft_id,
        "status": "sent",
        "outbox_filepath": str(outbox_file.relative_to(OUTBOX_DIR.parent)),
        "note": "Email written to local outbox (no actual SMTP send)",
    }

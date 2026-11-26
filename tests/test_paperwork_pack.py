"""Tests for Paperwork Pack MCP servers."""

import json
import sys
from pathlib import Path

import pytest

# Test data paths
REPO_ROOT = Path(__file__).resolve().parents[1]
DEMO_DATA = REPO_ROOT / "demo_data"
PACKS_ROOT = REPO_ROOT / "packs" / "paperwork"

# Add packs to Python path
sys.path.insert(0, str(REPO_ROOT))

# Import server modules
from packs.paperwork.bank import server as bank_server  # noqa: E402
from packs.paperwork.contacts import server as contacts_server  # noqa: E402
from packs.paperwork.documents import server as documents_server  # noqa: E402
from packs.paperwork.mail_drafts import server as mail_drafts_server  # noqa: E402
from packs.paperwork.notes import server as notes_server  # noqa: E402


class TestDocumentsServer:
    """Test the documents MCP server."""

    def test_list_files(self) -> None:
        """Test listing document files."""
        files = documents_server.list_files()
        assert isinstance(files, list)
        assert len(files) >= 2  # At least hospital bill and insurance notes

        filenames = [f["name"] for f in files]
        assert "lakeview_hospital_bill_oct2026.md" in filenames
        assert "health_insurance_policy_notes.md" in filenames

    def test_read_text_hospital_bill(self) -> None:
        """Test reading the hospital bill document."""
        content = documents_server.read_text("lakeview_hospital_bill_oct2026.md")
        assert isinstance(content, str)
        assert "Aarav Sharma" in content
        assert "LH-99214" in content
        assert "Rs 48,500" in content
        assert "billing@lakeview.example" in content
        assert "verify-refund@external-audit.example" in content

    def test_read_text_insurance_notes(self) -> None:
        """Test reading the insurance policy notes."""
        content = documents_server.read_text("health_insurance_policy_notes.md")
        assert isinstance(content, str)
        assert "Rs 2,000" in content
        assert "30 days" in content

    def test_read_text_nonexistent_file(self) -> None:
        """Test reading a file that doesn't exist."""
        with pytest.raises(FileNotFoundError):
            documents_server.read_text("nonexistent_file.md")

    def test_search_files(self) -> None:
        """Test searching for text in documents."""
        results = documents_server.search_files("hospital")
        assert isinstance(results, list)
        assert len(results) >= 1

        # Verify hospital bill is in results
        filenames = [r["name"] for r in results]
        assert "lakeview_hospital_bill_oct2026.md" in filenames


class TestBankServer:
    """Test the bank MCP server."""

    def test_query_transactions_all(self) -> None:
        """Test querying all transactions."""
        txns = bank_server.query_transactions()
        assert isinstance(txns, list)
        assert len(txns) >= 10  # Multiple transactions in demo data

    def test_query_transactions_by_account(self) -> None:
        """Test filtering transactions by account number."""
        txns = bank_server.query_transactions(account="4401928371")
        assert len(txns) >= 10
        assert all(txn["account"] == "4401928371" for txn in txns)

    def test_query_transactions_lakeview_hospital(self) -> None:
        """Test finding the Lakeview Hospital payment."""
        txns = bank_server.query_transactions(description="Lakeview Hospital")
        assert len(txns) == 1
        assert txns[0]["description"] == "Lakeview Hospital"
        assert txns[0]["amount"] == "52000.00"
        assert txns[0]["type"] == "DEBIT"

    def test_query_transactions_by_amount_range(self) -> None:
        """Test filtering by amount range."""
        txns = bank_server.query_transactions(min_amount=50000.0, max_amount=55000.0)
        assert len(txns) >= 1
        # Should include the hospital payment
        descriptions = [t["description"] for t in txns]
        assert "Lakeview Hospital" in descriptions

    def test_summarise_period_all(self) -> None:
        """Test summarizing all transactions."""
        summary = bank_server.summarise_period()
        assert isinstance(summary, dict)
        assert "total_credits" in summary
        assert "total_debits" in summary
        assert "count" in summary

        # Verify calculations
        total_debits = float(summary["total_debits"])
        assert total_debits > 50000.0  # Hospital payment alone is 52k

    def test_summarise_period_october(self) -> None:
        """Test summarizing October 2026 transactions."""
        summary = bank_server.summarise_period(start_date="2026-10-01", end_date="2026-10-31")
        count = int(summary["count"])
        assert count >= 10


class TestContactsServer:
    """Test the contacts MCP server."""

    def test_lookup_contact_by_name(self) -> None:
        """Test looking up a contact by exact name."""
        contact = contacts_server.lookup_contact("Aarav Sharma")
        assert contact is not None
        assert contact["name"] == "Aarav Sharma"
        assert contact["email"] == "aarav.sharma@example.com"
        assert contact["phone"] == "+91-98765-43210"

    def test_lookup_contact_by_alias(self) -> None:
        """Test looking up a contact by alias."""
        contact = contacts_server.lookup_contact("Aarav")
        assert contact is not None
        assert contact["name"] == "Aarav Sharma"

    def test_lookup_contact_lakeview_billing(self) -> None:
        """Test looking up Lakeview Hospital billing contact."""
        contact = contacts_server.lookup_contact("Lakeview Hospital Billing")
        assert contact is not None
        assert contact["email"] == "billing@lakeview.example"
        assert contact["category"] == "healthcare"

    def test_lookup_contact_not_found(self) -> None:
        """Test looking up a contact that doesn't exist."""
        contact = contacts_server.lookup_contact("Unknown Person")
        assert contact is None

    def test_lookup_email_by_name(self) -> None:
        """Test looking up email by contact name."""
        email = contacts_server.lookup_email("Lakeview Hospital Billing")
        assert email == "billing@lakeview.example"

    def test_lookup_email_passthrough(self) -> None:
        """Test that email addresses are passed through as-is."""
        email = contacts_server.lookup_email("test@example.com")
        assert email == "test@example.com"

    def test_lookup_email_not_found(self) -> None:
        """Test looking up email for unknown contact."""
        with pytest.raises(ValueError, match="No email found"):
            contacts_server.lookup_email("Unknown Person")

    def test_list_contacts_all(self) -> None:
        """Test listing all contacts."""
        contacts = contacts_server.list_contacts()
        assert isinstance(contacts, list)
        assert len(contacts) >= 5

        names = [c["name"] for c in contacts]
        assert "Aarav Sharma" in names
        assert "Lakeview Hospital Billing" in names

    def test_list_contacts_by_type(self) -> None:
        """Test filtering contacts by type."""
        personal_contacts = contacts_server.list_contacts(contact_type="personal")
        assert all(c["type"] == "personal" for c in personal_contacts)


class TestMailDraftsServer:
    """Test the mail_drafts MCP server."""

    def test_create_draft(self, tmp_path: Path) -> None:
        """Test creating an email draft."""
        # Temporarily override the drafts directory
        original_drafts_dir = mail_drafts_server.DRAFTS_DIR
        mail_drafts_server.DRAFTS_DIR = tmp_path / "drafts"
        mail_drafts_server.DRAFTS_DIR.mkdir()

        try:
            result = mail_drafts_server.create_draft(
                to="test@example.com",
                subject="Test Subject",
                body="Test body content",
                cc="cc@example.com",
            )

            assert "draft_id" in result
            assert result["status"] == "draft_created"

            # Verify file was created
            draft_file = mail_drafts_server.DRAFTS_DIR / f"{result['draft_id']}.json"
            assert draft_file.exists()

            # Verify content
            draft_data = json.loads(draft_file.read_text(encoding="utf-8"))
            assert draft_data["to"] == "test@example.com"
            assert draft_data["subject"] == "Test Subject"
            assert draft_data["body"] == "Test body content"
            assert draft_data["cc"] == "cc@example.com"
        finally:
            mail_drafts_server.DRAFTS_DIR = original_drafts_dir

    def test_list_drafts(self, tmp_path: Path) -> None:
        """Test listing email drafts."""
        original_drafts_dir = mail_drafts_server.DRAFTS_DIR
        mail_drafts_server.DRAFTS_DIR = tmp_path / "drafts"
        mail_drafts_server.DRAFTS_DIR.mkdir()

        try:
            # Create some drafts
            mail_drafts_server.create_draft(
                to="test1@example.com", subject="Draft 1", body="Body 1"
            )
            mail_drafts_server.create_draft(
                to="test2@example.com", subject="Draft 2", body="Body 2"
            )

            drafts = mail_drafts_server.list_drafts()
            assert len(drafts) >= 2  # At least 2 drafts
            subjects = [d["subject"] for d in drafts]
            assert "Draft 1" in subjects
            assert "Draft 2" in subjects
        finally:
            mail_drafts_server.DRAFTS_DIR = original_drafts_dir

    def test_read_draft(self, tmp_path: Path) -> None:
        """Test reading a specific draft."""
        original_drafts_dir = mail_drafts_server.DRAFTS_DIR
        mail_drafts_server.DRAFTS_DIR = tmp_path / "drafts"
        mail_drafts_server.DRAFTS_DIR.mkdir()

        try:
            result = mail_drafts_server.create_draft(
                to="test@example.com", subject="Test Draft", body="Test content"
            )
            draft_id = result["draft_id"]

            draft_data = mail_drafts_server.read_draft(draft_id)
            assert draft_data["draft_id"] == draft_id
            assert draft_data["subject"] == "Test Draft"
            assert draft_data["body"] == "Test content"
        finally:
            mail_drafts_server.DRAFTS_DIR = original_drafts_dir

    def test_read_draft_not_found(self, tmp_path: Path) -> None:
        """Test reading a draft that doesn't exist."""
        original_drafts_dir = mail_drafts_server.DRAFTS_DIR
        mail_drafts_server.DRAFTS_DIR = tmp_path / "drafts"
        mail_drafts_server.DRAFTS_DIR.mkdir()

        try:
            with pytest.raises(FileNotFoundError):
                mail_drafts_server.read_draft("nonexistent_draft")
        finally:
            mail_drafts_server.DRAFTS_DIR = original_drafts_dir

    def test_send_draft(self, tmp_path: Path) -> None:
        """Test sending a draft (writes to outbox)."""
        original_drafts_dir = mail_drafts_server.DRAFTS_DIR
        original_outbox_dir = mail_drafts_server.OUTBOX_DIR
        mail_drafts_server.DRAFTS_DIR = tmp_path / "drafts"
        mail_drafts_server.OUTBOX_DIR = tmp_path / "outbox"
        mail_drafts_server.DRAFTS_DIR.mkdir()
        mail_drafts_server.OUTBOX_DIR.mkdir()

        try:
            # Create a draft
            result = mail_drafts_server.create_draft(
                to="recipient@example.com", subject="Important Email", body="Important content"
            )
            draft_id = result["draft_id"]

            # Send the draft
            send_result = mail_drafts_server.send_draft(draft_id)
            assert send_result["status"] == "sent"
            assert "outbox_filepath" in send_result

            # Verify outbox file was created
            outbox_file = mail_drafts_server.OUTBOX_DIR / f"sent_{draft_id}.json"
            assert outbox_file.exists()

            # Verify content
            outbox_data = json.loads(outbox_file.read_text(encoding="utf-8"))
            assert outbox_data["status"] == "sent"
            assert "sent_at" in outbox_data
            assert outbox_data["to"] == "recipient@example.com"
        finally:
            mail_drafts_server.DRAFTS_DIR = original_drafts_dir
            mail_drafts_server.OUTBOX_DIR = original_outbox_dir


class TestNotesServer:
    """Test the notes MCP server."""

    def test_search_notes(self) -> None:
        """Test searching for text in notes."""
        results = notes_server.search_notes("health")
        assert isinstance(results, list)
        assert len(results) >= 1

    def test_search_notes_medical(self) -> None:
        """Test searching for medical-related notes."""
        results = notes_server.search_notes("medical")
        assert len(results) >= 1
        excerpts = [r["excerpt"] for r in results]
        assert any("medical" in e.lower() for e in excerpts)

    def test_read_note(self) -> None:
        """Test reading a specific note file."""
        content = notes_server.read_note("personal_notes.md")
        assert isinstance(content, str)
        assert "Medical Reminders" in content

    def test_read_note_not_found(self) -> None:
        """Test reading a note that doesn't exist."""
        with pytest.raises(FileNotFoundError):
            notes_server.read_note("nonexistent_note.md")

    def test_list_notes(self) -> None:
        """Test listing all notes."""
        notes = notes_server.list_notes()
        assert isinstance(notes, list)
        assert len(notes) >= 1
        names = [n["name"] for n in notes]
        assert "personal_notes.md" in names

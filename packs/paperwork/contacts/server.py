"""Contacts MCP server - read-only access to contact information."""

import json
from pathlib import Path

# Default contacts directory
CONTACTS_DIR = Path(__file__).parent.parent.parent.parent / "demo_data" / "contacts"


def _load_contacts() -> list[dict[str, str]]:
    """Load contacts from the contacts.json file."""
    contacts_file = CONTACTS_DIR / "contacts.json"
    if not contacts_file.exists():
        return []

    try:
        with contacts_file.open(encoding="utf-8") as f:
            data = json.load(f)
            return data.get("contacts", [])
    except (OSError, json.JSONDecodeError):
        return []


def lookup_contact(name: str) -> dict[str, str] | None:
    """Look up a contact by name or alias.

    Args:
        name: Name or alias to search for. Placeholders like [PERSON_1] are accepted.

    Returns:
        Contact information including email, phone, and category, or None if not found.
    """
    contacts = _load_contacts()
    name_lower = name.lower()

    for contact in contacts:
        # Check exact name match
        if contact.get("name", "").lower() == name_lower:
            return {
                "name": contact.get("name", ""),
                "email": contact.get("email", ""),
                "phone": contact.get("phone", ""),
                "type": contact.get("type", ""),
                "category": contact.get("category", ""),
                "relation": contact.get("relation", ""),
            }

        # Check aliases
        aliases = contact.get("aliases", [])
        if any(alias.lower() == name_lower for alias in aliases):
            return {
                "name": contact.get("name", ""),
                "email": contact.get("email", ""),
                "phone": contact.get("phone", ""),
                "type": contact.get("type", ""),
                "category": contact.get("category", ""),
                "relation": contact.get("relation", ""),
            }

    return None


def lookup_email(email_or_name: str) -> str:
    """Look up an email address by contact name or return the email if already an address.

    Args:
        email_or_name: Email address or contact name. Placeholders like [EMAIL_1] or [PERSON_1] are accepted.

    Returns:
        Email address of the contact.
    """
    # If it looks like an email, return it as-is
    if "@" in email_or_name:
        return email_or_name

    # Otherwise, look it up as a contact name
    contact = lookup_contact(email_or_name)
    if contact and contact.get("email"):
        return contact["email"]

    raise ValueError(f"No email found for contact: {email_or_name}")


def list_contacts(contact_type: str = "") -> list[dict[str, str]]:
    """List all contacts, optionally filtered by type.

    Args:
        contact_type: Filter by contact type (personal, work, service_provider) - optional.

    Returns:
        List of contacts with basic information.
    """
    contacts = _load_contacts()

    if not contact_type:
        return [
            {
                "name": c.get("name", ""),
                "email": c.get("email", ""),
                "type": c.get("type", ""),
                "category": c.get("category", ""),
            }
            for c in contacts
        ]

    # Filter by type
    return [
        {
            "name": c.get("name", ""),
            "email": c.get("email", ""),
            "type": c.get("type", ""),
            "category": c.get("category", ""),
        }
        for c in contacts
        if c.get("type", "").lower() == contact_type.lower()
    ]

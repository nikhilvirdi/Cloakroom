"""Tool card schema rewriter for placeholder compatibility."""

from __future__ import annotations

import copy
from typing import Any

from cloakroom.discovery.catalog import ToolEntry


def _relax_string_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Remove strict string validators that would reject placeholders.

    Args:
        schema: JSON schema object

    Returns:
        Relaxed schema with format/pattern constraints removed
    """
    relaxed = copy.deepcopy(schema)

    # Remove format constraints (email, uri, etc.)
    if "format" in relaxed:
        del relaxed["format"]

    # Remove pattern constraints
    if "pattern" in relaxed:
        del relaxed["pattern"]

    # Recursively process nested schemas
    if "properties" in relaxed and isinstance(relaxed["properties"], dict):
        for key, prop_schema in relaxed["properties"].items():
            if isinstance(prop_schema, dict):
                relaxed["properties"][key] = _relax_string_schema(prop_schema)

    if "items" in relaxed and isinstance(relaxed["items"], dict):
        relaxed["items"] = _relax_string_schema(relaxed["items"])

    if "additionalProperties" in relaxed and isinstance(relaxed["additionalProperties"], dict):
        relaxed["additionalProperties"] = _relax_string_schema(relaxed["additionalProperties"])

    return relaxed


def _add_placeholder_note(description: str) -> str:
    """Add a note about placeholder acceptance to the description.

    Args:
        description: Original tool description

    Returns:
        Description with placeholder note appended
    """
    placeholder_note = " Placeholders such as [EMAIL_1] or [PERSON_1] are accepted."

    # Avoid duplicate notes
    if "placeholders" in description.lower() or "[email_" in description.lower():
        return description

    return description + placeholder_note


def create_tool_card(
    tool: ToolEntry, relations: dict[str, list[str]] | None = None
) -> dict[str, Any]:
    """Create a rewritten tool card for the host.

    Args:
        tool: Tool entry from catalog
        relations: Optional tool relation hints (e.g., {"mail_drafts.create_draft": ["contacts.lookup_email"]})

    Returns:
        Tool card with relaxed schema and metadata
    """
    # Relax input schema
    relaxed_schema = _relax_string_schema(tool.input_schema)

    # Add placeholder note to description
    enhanced_description = _add_placeholder_note(tool.description)

    # Build tool card
    card: dict[str, Any] = {
        "tool_id": tool.tool_id,
        "name": tool.tool_name,
        "description": enhanced_description,
        "input_schema": relaxed_schema,
        "effect": tool.effect.value,
    }

    # Add relation hints if available
    if relations and tool.tool_id in relations:
        card["related_tools"] = relations[tool.tool_id]

    return card


def create_discovery_response(
    tools: list[ToolEntry],
    total_tools: int,
    total_tokens: int,
    relations: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    """Create a complete discovery response with tool cards and metadata.

    Args:
        tools: List of discovered tools
        total_tools: Total number of tools in catalog
        total_tokens: Total approximate tokens for all tools
        relations: Optional tool relation hints

    Returns:
        Discovery response dict
    """
    # Calculate exposed metrics
    exposed_tools = len(tools)
    exposed_tokens = sum(tool.tokens_approx for tool in tools)

    # Create tool cards
    tool_cards = [create_tool_card(tool, relations) for tool in tools]

    # Collect unique relation hints mentioned in returned tools
    hints = []
    if relations:
        for tool in tools:
            if tool.tool_id in relations:
                for related_id in relations[tool.tool_id]:
                    hint = f"{tool.tool_id} usually needs {related_id}"
                    if hint not in hints:
                        hints.append(hint)

    return {
        "tools": tool_cards,
        "hints": hints,
        "catalog": {
            "exposed": exposed_tools,
            "total": total_tools,
            "exposed_tokens_approx": exposed_tokens,
            "total_tokens_approx": total_tokens,
        },
    }

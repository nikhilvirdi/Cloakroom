"""Effect classification for tools based on annotations and configuration."""

from __future__ import annotations

from typing import Any

from cloakroom.contracts import EffectClass


def classify_effect(
    tool_id: str,
    annotations: dict[str, Any] | None = None,
    config_overrides: dict[str, EffectClass] | None = None,
) -> EffectClass:
    """Classify a tool's effect based on priority order.

    Priority (highest to lowest):
    1. User configuration override
    2. MCP tool annotations (readOnlyHint, destructiveHint, openWorldHint)
    3. Default UNKNOWN (treated as EXTERNAL)

    Args:
        tool_id: Tool identifier (server.tool format)
        annotations: MCP tool annotations from server
        config_overrides: User-configured effect overrides

    Returns:
        Effect classification for the tool
    """
    # Priority 1: Check configuration overrides
    if config_overrides and tool_id in config_overrides:
        return config_overrides[tool_id]

    # Priority 2: Check MCP annotations
    if annotations:
        # readOnlyHint → READ
        if annotations.get("readOnlyHint") is True:
            return EffectClass.READ

        # destructiveHint → check if it's local or external
        # For now, destructive without openWorld is LOCAL_WRITE
        if annotations.get("destructiveHint") is True:
            if annotations.get("openWorldHint") is True:
                return EffectClass.EXTERNAL
            return EffectClass.LOCAL_WRITE

        # openWorldHint alone → EXTERNAL
        if annotations.get("openWorldHint") is True:
            return EffectClass.EXTERNAL

    # Priority 3: Default to UNKNOWN (fail-safe, requires approval)
    return EffectClass.UNKNOWN

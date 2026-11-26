"""Frozen shared contracts between Dev A and Dev B modules.

This file defines every cross-boundary data model and Protocol shared between
the privacy core (vault, cloak, control room) and the MCP runtime (discovery,
policy, gateway). Both developers code against these exact names and signatures.

Created in Phase 0 and frozen thereafter. No edits during feature branches.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol


class EffectClass(StrEnum):
    """Effect classification for tool calls."""

    READ = "read"
    LOCAL_WRITE = "local_write"
    EXTERNAL = "external"
    UNKNOWN = "unknown"


class ApprovalStatus(StrEnum):
    """Status of an approval request."""

    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"


@dataclass(frozen=True)
class CloakedEntity:
    """A single cloaked entity with its placeholder and metadata."""

    placeholder: str  # e.g. "[PERSON_1]"
    entity_type: str  # e.g. "PERSON", "MED_ID", "ACCT", "EMAIL"
    tier: str  # "identifier" | "contextual" | "analytical"
    stage: str  # "field_policy" | "gazetteer" | "detector"


@dataclass(frozen=True)
class CloakResult:
    """Result of cloaking a payload through the privacy pipeline."""

    cloaked_payload: Any  # Safe to send to cloud host
    raw_payload: Any  # In-memory local original only — NEVER published to EventBus or persisted to audit; Control Room reconstructs from vault
    entities: list[CloakedEntity] = field(default_factory=list)
    tripwire_passed: bool = True
    withheld: bool = False
    withhold_reason: str | None = None
    latency_ms: float = 0.0


@dataclass(frozen=True)
class RestoreResult:
    """Result of restoring placeholders to real values."""

    restored_arguments: dict[str, Any]
    used_placeholders: list[CloakedEntity]
    contains_identifier_tier: bool
    blocked: bool = (
        False  # True when invented/unknown placeholders found — caller MUST NOT call downstream
    )
    unknown_placeholders: list[str] = field(
        default_factory=list
    )  # Token strings ONLY (e.g. "[PERSON_99]") — never real values


@dataclass(frozen=True)
class CatalogMetrics:
    """Discovery catalog metrics for the Control Room."""

    exposed_tools: int
    total_tools: int
    exposed_tokens_approx: int
    total_tokens_approx: int


@dataclass(frozen=True)
class ApprovalRequest:
    """An approval request for an external or unknown effect."""

    approval_id: str
    tool_id: str
    effect: EffectClass
    payload_hash: str
    restored_arguments: dict[str, Any]
    cloaked_arguments: dict[str, Any]
    risk_flags: list[str]  # e.g. ["UNKNOWN_RECIPIENT", "IDENTIFIER_EXPOSURE: ACCT_1"]
    created_at: datetime
    status: ApprovalStatus = ApprovalStatus.PENDING


@dataclass(frozen=True)
class GatewayEvent:
    """An event emitted by the gateway for audit and Control Room display."""

    event_id: str
    event_type: (
        str  # "discovery" | "tool_call" | "approval_requested" | "approval_resolved" | "error"
    )
    timestamp: datetime
    tool_id: str | None = None
    effect: EffectClass | None = None
    cloud_view: Any = None  # Strictly cloaked data
    local_view: Any = None  # Cloaked view + entity tokens; Control Room reconstructs raw values FROM THE VAULT on Reveal (token-gated), never stored on the event
    entities: list[CloakedEntity] = field(default_factory=list)
    latency_ms: float = 0.0
    tripwire_passed: bool = True
    decision: str | None = None
    approval: ApprovalRequest | None = None
    catalog_metrics: CatalogMetrics | None = None


class CloakEngineProtocol(Protocol):
    """Protocol for the cloak pipeline and vault (Dev A implements)."""

    def cloak(self, payload: Any, *, server_id: str = "", tool_name: str = "") -> CloakResult: ...

    def restore(self, arguments: dict[str, Any]) -> RestoreResult: ...

    def list_vault_summary(self) -> list[dict[str, Any]]: ...


class ApprovalResolverProtocol(Protocol):
    """Protocol for approval resolution (Dev B implements)."""

    async def resolve(
        self, approval_id: str, *, approved: bool, payload_hash: str
    ) -> ApprovalRequest: ...

    def list_pending(self) -> list[ApprovalRequest]: ...


class EventBusProtocol(Protocol):
    """Protocol for event publication and history (Dev A implements)."""

    async def publish(self, event: GatewayEvent) -> None: ...

    def get_history(self) -> list[GatewayEvent]: ...


class ControlRoomFactory(Protocol):
    """Dev A implements; Dev B calls exactly this signature from `cloakroom serve`."""

    def __call__(
        self,
        *,
        event_bus: EventBusProtocol,
        approvals: ApprovalResolverProtocol,
        token: str,
    ) -> Any: ...

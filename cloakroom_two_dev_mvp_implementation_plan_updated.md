# Cloakroom — Two-Developer Zero-Conflict MVP Implementation Plan

This plan divides all remaining work for the **Cloakroom MVP** between **Dev A** and **Dev B** based on the current repository state. It guarantees **zero merge conflicts** through strict directory ownership, a 15-minute shared contract commit (Phase 0), and independent mock/harness testing before integration.

---

## 1. Current Baseline (Already Done — Do Not Rewrite)

| Area | Status | Rule for MVP Sprint |
| --- | --- | --- |
| Docs & specs (`README.md`, `docs/*.md`, 7 SVGs) | Done | **Read-only source of truth** during build. Update `README.md` only at the very end with real benchmark numbers. |
| Engineering foundation (`pyproject.toml`, `uv.lock`, CI, pre-commit) | Done | Update dependencies **once** in Phase 0 on `main`. Do not edit during feature branches. |
| Configuration subsystem (`configuration/loader.py`, `models.py`, `error`, `observability`) | Done | **Reuse directly.** Do not recreate config schemas, error types, or loggers. |
| Existing CLI (`cloakroom check-config`) & 391 lines of green tests | Done | Keep all existing tests green (`ruff`, `mypy src`, `pytest` on Py 3.11–3.14 / Ubuntu & Windows). |
| Example configs (`config/*.example.yaml`) | Done | Keep intact; add separate `config/demo.*.yaml` files if needed for the live demo. |

### Remaining MVP Scope (0% Built — To Be Split)
* `src/cloakroom/vault/` & `src/cloakroom/cloak/`
* `src/cloakroom/controlroom/`
* `src/cloakroom/discovery/`, `src/cloakroom/policy/`, `src/cloakroom/gateway/`
* Paperwork Pack local MCP servers (4 core MVP servers + optional `notes`) & synthetic demo data
* `cloakroom serve` CLI wiring, offline `replay_agent.py`, and `benchmarks/`

### Explicitly Deferred (Out of MVP Scope)
* `cloakroom init` Claude Desktop config importer
* Presidio / spaCy NER fallback
* OS `keyring` GUI prompts (use AES-256-GCM with a local `0600` keyfile for MVP; keep `keyring` optional)
* `vault wipe` / `vault rotate` CLI subcommands

---

## 2. Zero-Conflict Ownership Matrix

**Golden Rule:** Neither developer may create, edit, or format files outside their owned paths while working on feature branches.

| Path / Module | Exclusive Owner | Notes |
| --- | --- | --- |
| `pyproject.toml`, `uv.lock`, `src/cloakroom/contracts.py` | **Phase 0 (Frozen on `main`)** | Committed together in 15 mins before branching. Frozen afterward. |
| `tests/conftest.py`, `tests/fixtures/*` | **Phase 0 (Frozen on `main`)** | Shared test scaffolding already in the repo. Each dev embeds its own test data inside its own `tests/test_*.py` file instead of editing fixtures/conftest. |
| `src/cloakroom/configuration/*`, `error*`, `observability*` | **Frozen (Existing)** | Import only. If a field is needed, agree on a quick 1-line PR to `main`. |
| `src/cloakroom/vault/*` | **Dev A** | SQLite vault, normalization, AES-256-GCM, placeholder minting/lookup. |
| `src/cloakroom/cloak/*` | **Dev A** | 6-stage cloak pipeline, gazetteer, detectors, restore engine, tripwire. |
| `src/cloakroom/controlroom/*` | **Dev A** | FastAPI + Uvicorn SSE server, event bus, single-file HTML/CSS/JS UI. |
| `benchmarks/*` | **Dev A** | `run_eval.py` (leak, control, discovery, latency) + results JSON/MD. |
| `tests/test_vault.py`, `tests/test_cloak.py`, `tests/test_controlroom.py` | **Dev A** | Unit + SSE/HTTP tests for Dev A's modules. |
| `src/cloakroom/discovery/*` | **Dev B** | Tool catalog, BM25 (+ optional lazy MiniLM RRF), schema relaxation, token meter. |
| `src/cloakroom/policy/*` | **Dev B** | Effect classes, SHA-256 hash binding, risk flags, async `ApprovalManager`. |
| `src/cloakroom/gateway/*` | **Dev B** | Front stdio MCP server, downstream `ClientPool`, end-to-end orchestration. |
| `src/cloakroom/cli.py` | **Dev B** | Exclusive owner for adding the `cloakroom serve` command. |
| Paperwork Pack server folders (`documents`, `bank`, `contacts`, `mail_drafts`, `notes`) | **Dev B** | Lightweight `FastMCP` local servers reading synthetic files. |
| `demo_data/*`, `demo/*`, `config/demo.*` | **Dev B** | Hospital bill scenario, prompt-injection/external-audit case, `replay_agent.py`. |
| `tests/test_paperwork_pack.py`, `tests/test_discovery.py`, `tests/test_policy.py`, `tests/test_gateway_e2e.py` | **Dev B** | Server, discovery, policy, and integration tests. |

### Git Branching Workflow
1. Complete **Phase 0** directly on `main` (or via one fast PR) and push.
2. **Dev A** branches: `git checkout -b feat/dev-a-privacy-ui`
3. **Dev B** branches: `git checkout -b feat/dev-b-mcp-runtime`
4. Both push small commits frequently and run `uv run ruff check . && uv run mypy src && uv run pytest` before opening PRs.
5. **Merge Order at Integration:** Merge `feat/dev-a-privacy-ui` → `main` first (zero conflicts), then rebase/merge `feat/dev-b-mcp-runtime` → `main` (zero conflicts), then Dev B completes the 20-line wiring swap in `gateway/app.py` (replacing test stubs with Dev A's concrete classes).
6. **Test layout note:** the flat `tests/test_*.py` files named in this plan are intentional — they coexist with the repo's existing `tests/unit/`, `tests/integration/`, `tests/security/` (pytest discovers all of them). Do not move, rename, or refactor existing test directories, and never edit `tests/conftest.py` or `tests/fixtures/` (frozen in Phase 0).

---

## 3. Phase 0: Shared Lock-In Commit (15 Minutes Together on `main`)

Before either dev starts coding, execute these two steps together on `main`:

### Step 0.1 — Lock Dependencies Once
Verify `pyproject.toml` includes the MVP runtime dependencies (remove/defer heavy optional ones like `spacy`/`presidio` for now) and run `uv lock`:
* `mcp` (official Python MCP SDK, includes `FastMCP` and stdio client/server)
* `fastapi`, `uvicorn` (Control Room local HTTP + SSE server)
* `cryptography` (AES-256-GCM + HMAC-SHA256)
* `pyahocorasick` (or `ahocorasick_rs` — verify Windows wheel availability in CI!)
* `rank-bm25` (fast zero-cold-start tool retrieval; add `sentence-transformers` only if pre-cached and lazy-loaded)
* `httpx` (dev dependency for testing FastAPI endpoints)

> **Windows CI Note:** `pyahocorasick` sometimes requires a C compiler on Windows Python 3.14; check `uv sync` on your CI matrix immediately in Phase 0. If it fails on Py 3.14 Windows, swap to `ahocorasick-rs` or a pure-Python Trie fallback in `contracts`/Phase 0 right now so CI stays green.

### Step 0.2 — Create `src/cloakroom/contracts.py`
Commit a single file defining every cross-boundary data model and `Protocol` shared between Dev A and Dev B:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol


class EffectClass(StrEnum):
    READ = "read"
    LOCAL_WRITE = "local_write"
    EXTERNAL = "external"
    UNKNOWN = "unknown"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"


@dataclass(frozen=True)
class CloakedEntity:
    placeholder: str  # e.g. "[PERSON_1]"
    entity_type: str  # e.g. "PERSON", "MED_ID", "ACCT", "EMAIL"
    tier: str  # "identifier" | "contextual" | "analytical"
    stage: str  # "field_policy" | "gazetteer" | "detector"


@dataclass(frozen=True)
class CloakResult:
    cloaked_payload: Any  # Safe to send to cloud host
    raw_payload: Any  # In-memory local original only — NEVER published to EventBus or persisted to audit; Control Room reconstructs from vault
    entities: list[CloakedEntity] = field(default_factory=list)
    tripwire_passed: bool = True
    withheld: bool = False
    withhold_reason: str | None = None
    latency_ms: float = 0.0


@dataclass(frozen=True)
class RestoreResult:
    restored_arguments: dict[str, Any]
    used_placeholders: list[CloakedEntity]
    contains_identifier_tier: bool
    blocked: bool = (
        False  # True when invented/unknown placeholders found — caller MUST NOT call downstream
    )
    unknown_placeholders: list[
        str
    ] = []  # Token strings ONLY (e.g. "[PERSON_99]") — never real values


@dataclass(frozen=True)
class CatalogMetrics:
    exposed_tools: int
    total_tools: int
    exposed_tokens_approx: int
    total_tokens_approx: int


@dataclass(frozen=True)
class ApprovalRequest:
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
    def cloak(self, payload: Any, *, server_id: str = "", tool_name: str = "") -> CloakResult: ...
    def restore(self, arguments: dict[str, Any]) -> RestoreResult: ...
    def list_vault_summary(self) -> list[dict[str, Any]]: ...


class ApprovalResolverProtocol(Protocol):
    async def resolve(
        self, approval_id: str, *, approved: bool, payload_hash: str
    ) -> ApprovalRequest: ...
    def list_pending(self) -> list[ApprovalRequest]: ...


class EventBusProtocol(Protocol):
    async def publish(self, event: GatewayEvent) -> None: ...
    def get_history(self) -> list[GatewayEvent]: ...


class ControlRoomFactory(Protocol):
    """Dev A implements; Dev B calls exactly this signature from `cloakroom serve`."""

    def __call__(
        self, *, event_bus: EventBusProtocol, approvals: ApprovalResolverProtocol, token: str
    ) -> Any: ...
```

---

## 4. Dev A Task Plan — Privacy Core, Control Room UI & Benchmarks

**Branch:** `feat/dev-a-privacy-ui`  
**Owned Paths:** `src/cloakroom/vault/`, `src/cloakroom/cloak/`, `src/cloakroom/controlroom/`, `benchmarks/`, `tests/test_vault.py`, `tests/test_cloak.py`, `tests/test_controlroom.py`

### Block A1: Encrypted SQLite Vault (`src/cloakroom/vault/`) — ~3 Hours
* [ ] **A1.1 Canonicalizer:** Normalize strings before lookup (strip whitespace, lowercase, strip honorifics `Mr./Ms./Dr.`, strip spaces/dashes in digits for phone/account/IDs). Map gazetteer aliases (e.g., `"Aarav"`, `"Aarav Sharma"`, `"Mr. Aarav Sharma"`) to one canonical entity. No fuzzy name merging.
* [ ] **A1.2 SQLite Storage + AES-256-GCM:** Store `hmac_keyed_hash`, `entity_type`, `placeholder` (`[PERSON_1]`, `[MED_ID_1]`, `[ACCT_1]`, `[EMAIL_1]`, `[ORG_1]`, `[PHONE_1]`, `[GOVID_1]`, `[ADDR_1]`, `[SECRET_1]`), `tier`, and `encrypted_value` in SQLite. Auto-generate a local keyfile (`0600`) in the data directory so it never blocks on OS keychain prompts.
* [ ] **A1.3 Stable Minting & Lookup:** `get_or_mint(raw_value, entity_type, tier)` returns the exact same `[TYPE_N]` across restarts and tools. `resolve_placeholder(placeholder)` returns `(raw_value, entity_type, tier)` or raises a typed unknown-placeholder error.
* [ ] **A1.4 Tests (`tests/test_vault.py`):** Stability across reopen, alias canonicalization, encryption at rest (raw string not present in `.db` bytes), unknown placeholder rejection.

### Block A2: 6-Stage Cloak & Restore Pipeline (`src/cloakroom/cloak/`) — ~4 Hours
* [ ] **A2.1 Content Filter:** Walk nested dicts/lists/strings; replace binary/image blocks (base64 images, `type == "image"`) with `"[BINARY_CONTENT_WITHHELD]"`.
* [ ] **A2.2 Field Policy:** Mask configured structured field keys (`account_no`, `patient_name`, `email`, `uhid`, etc.) deterministically before free-text scanning.
* [ ] **A2.3 Gazetteer Sweep:** Load user profile, contacts, and orgs from existing config models; run longest-non-overlapping multi-pattern matching (`ahocorasick` or fast regex trie) so `"Aarav Sharma"` matches before `"Aarav"`. Protect already-minted `[TYPE_N]` spans from re-matching.
* [ ] **A2.4 Checksum-Validated Detectors:**
  * Aadhaar (12-digit + Verhoeff checksum)
  * Card numbers (Luhn checksum)
  * PAN (`[A-Z]{5}[0-9]{4}[A-Z]`), IFSC (`[A-Z]{4}0[A-Z0-9]{6}`)
  * Email, Indian/international phone, medical record IDs (`UHID` / `LH-\d+`), API keys, and custom regexes from config.
  * Keep **Analytical tier** (amounts like `Rs 48,500`, dates, counts) visible by default.
* [ ] **A2.5 Fail-Closed Tripwire:** Rescan the final cloaked output against every known plaintext in the vault and gazetteer. If hit, re-cloak once; if hit a second time, return `withheld=True` with a safe notice and `tripwire_passed=False`.
* [ ] **A2.6 Restore Engine:** Traverse `arguments` dict/lists/strings, locate all `[TYPE_N]` tokens. For any invented/unknown placeholder, set `RestoreResult.blocked=True` and list the token strings in `unknown_placeholders` (tokens ONLY — never real values), leaving those arguments unrestored; otherwise replace with real values. Flag `contains_identifier_tier=True` if any `identifier`-tier token was restored. (Dev B's gateway converts `blocked=True` into the host-facing MCP error listing valid placeholder **types** — raised BEFORE any downstream call.)
* [ ] **A2.7 Tests (`tests/test_cloak.py`):** Test the exact README hospital bill, bank export, error message echoing a path/name, overlapping names, invalid checksums (no false positives), invented placeholder rejection, and tripwire fail-closed behavior.

### Block A3: Control Room Server & Polished Single-File UI (`src/cloakroom/controlroom/`) — ~4 Hours
* [ ] **A3.1 In-Memory Event Bus:** Implement `EventBusProtocol` with `asyncio.Queue` fan-out to connected SSE clients plus an in-memory rolling history + SQLite `audit_events` persistence. **Persist cloaked events only** — the audit log records calls, decisions and withheld payloads, never raw private values (per ARCHITECTURE.md/INTERFACE.md); the Control Room reconstructs local-view values from the vault at display time.
* [ ] **A3.2 FastAPI App (Embedded-Ready):** Bind strictly to `127.0.0.1` with a startup `secrets.token_urlsafe(24)` query/header token.
  * `GET /?token=...` — serves single-file `index.html`
  * `GET /api/events?token=...` — SSE stream emitting historical + live `GatewayEvent` JSON
  * `GET /api/state?token=...` — initial hydration (catalog metrics, pending approvals, vault summary, policy tiers); local-pane values are reconstructed from the vault here, at request time — events/audit rows never carry raw payloads
  * `POST /api/approvals/{approval_id}/decision?token=...` — calls `ApprovalResolverProtocol.resolve(...)` with `{approved: bool, payload_hash: str}`
  * **Critical:** Configure Uvicorn with `log_config=None` and `access_log=False` (or strictly `stderr`) so zero bytes ever leak to `stdout`.
  * **Factory:** expose exactly `create_control_room(event_bus, approvals, token)` per the `ControlRoomFactory` signature frozen in `contracts.py` — Dev B calls it verbatim from `cloakroom serve`.
* [ ] **A3.3 Single-File Dark-Mode Dashboard (`index.html`):**
  * **Top Command Bar:** Green `127.0.0.1` status indicator, **Catalog Meter** (`6 / 24 tools exposed • ~75% tokens saved`), **Entities Cloaked / 0 Leaked** counter, global **"Reveal Local Values"** toggle (OFF/blurred by default), and 2 tabs (`Live & Approvals` | `Vault & Audit`).
  * **Main Split View (Left 65%):** Chronological **Live Cloak Feed** cards showing timestamp, `tool_id`, effect pill (`READ` blue / `LOCAL_WRITE` amber / `EXTERNAL` red), latency (`ms`), Tripwire badge (`PASS`/`WITHHELD`), and crisp **2-column side-by-side diff (`Laptop Saw` vs. `Cloud Saw`)** with color-coded `[TYPE_N]` badges.
  * **Right Sidebar (35%):** **Pending Approvals Queue** flashing on new `external` calls, displaying restored recipient, restored body (highlighting identifier values), red risk chips (`⚠ UNKNOWN RECIPIENT`, `⚠ IDENTIFIER EXPOSURE`), truncated SHA-256 hash, and **Approve & Execute** / **Deny** buttons.
  * **Secondary Tab (`Vault & Audit`):** Read-only active placeholder table, privacy tier summary, and audit event table with Export JSON button.
* [ ] **A3.4 Standalone Mock Runner & Tests (`tests/test_controlroom.py`):** Add a helper (`python -m cloakroom.controlroom.dev_preview`) that emits sample events so Dev A can visually polish the UI independently of Dev B. Test token auth (401 without token), SSE streaming, and approve/deny routing.

### Block A4: Automated Benchmarks (`benchmarks/`) — ~2 Hours (Post-Merge or Parallel)
* [ ] **A4.1 `benchmarks/run_eval.py`:** Run 4 scripted measurements and print a clean Markdown table + save `benchmarks/results.json`:
  1. **Leak test:** Seeded synthetic PII corpus (with vs. without gazetteer) → `% leaked` (target `0%`).
  2. **Control test:** Unauthorized `external` / `unknown` calls attempted without approval → `% blocked` (target `100%`).
  3. **Discovery test:** Needed-tool recall@6 & approximate schema token reduction across 22+ tools.
  4. **Overhead test:** p50 and p95 latency in milliseconds for cloaking and discovery.

---

## 5. Dev B Task Plan — Paperwork Pack, Discovery, Policy, MCP Gateway & Demo Wiring

**Branch:** `feat/dev-b-mcp-runtime`  
**Owned Paths:** Paperwork Pack folders, `demo_data/`, `demo/`, `config/demo.*`, `src/cloakroom/discovery/`, `src/cloakroom/policy/`, `src/cloakroom/gateway/`, `src/cloakroom/cli.py`, `tests/test_paperwork_pack.py`, `tests/test_discovery.py`, `tests/test_policy.py`, `tests/test_gateway_e2e.py`

### Block B1: Synthetic Demo Data & Paperwork Pack MCP Servers — ~3 Hours
* [ ] **B1.1 Synthetic `demo_data/`:** Create clean, consistent synthetic files for **Aarav Sharma**:
  * `documents/lakeview_hospital_bill_oct2026.md`: Patient `Aarav Sharma`, UHID `LH-99214`, Hospital `Lakeview Hospital`, Total billed `Rs 48,500`, Billing contact `billing@lakeview.example`, plus an explicit **External Billing Audit Footer** (used for Demo Beat 3: instructs sending account details to `verify-refund@external-audit.example`).
  * `documents/health_insurance_policy_notes.md`: Policy clause covering hospital billing overcharges > Rs 2,000 when disputed within 30 days.
  * `bank/transactions_oct2026.csv`: Account `4401928371`, holder `Aarav Sharma`, debit `Rs 52,000` to `Lakeview Hospital` (creating an exact `Rs 3,500` discrepancy) + 10 realistic filler rows.
  * `contacts/contacts.json`: `Lakeview Hospital Billing` (`billing@lakeview.example`), `Aarav Sharma` (`aarav.sharma@example.com`, alias `Aarav`, phone `+91-98765-43210`). Deliberately omit `verify-refund@external-audit.example` so Unknown Recipient flagging fires reliably.
  * `mail/drafts/` & `mail/outbox/` folders.
* [ ] **B1.2 4 Local `FastMCP` Servers (plus 10–15 lightweight catalog tools):**
  * `documents`: `list_files`, `read_text`, `search_files` (`readOnlyHint=True`)
  * `bank`: `query_transactions`, `summarise_period` (`readOnlyHint=True`)
  * `contacts`: `lookup_contact`, `lookup_email` (`readOnlyHint=True`)
  * `mail_drafts`: `create_draft` (`local_write`), `list_drafts` (`read`), `send_draft` (`external` — writes JSON/Markdown into `mail/outbox/` so judges can inspect the exact restored email without SMTP/OAuth risk).
  * *(Optional quick win)* `notes`: `search_notes`, `read_note` + extra read-only utility tools (or wrap the reference filesystem server) so total indexed catalog reaches **20–24 tools** for a compelling Catalog Meter savings readout.
* [ ] **B1.3 Tests (`tests/test_paperwork_pack.py`):** Verify every tool executes cleanly over stdio and returns expected synthetic data with UTF-8 encoding.

### Block B2: Tool Discovery & Schema Relaxation (`src/cloakroom/discovery/`) — ~3 Hours
* [ ] **B2.1 In-Memory Catalog & Token Estimator:** Store downstream `server_id`, `tool_name`, `tool_id` (`server.tool`), description, input JSON schema, effect class, and approximate token count (`len(json.dumps(schema)) // 4`).
* [ ] **B2.2 Hybrid Retrieval (`discover_tools`):** Implement fast **BM25** (`rank-bm25`) with synonym expansion (`bill` ↔ `invoice`, `mail` ↔ `email`, `bank` ↔ `transaction`) so startup is < 200ms offline. Add optional background lazy-loading of `all-MiniLM-L6-v2` with Reciprocal Rank Fusion **only** if time permits and `HF_HUB_OFFLINE=1` works cleanly.
* [ ] **B2.3 Tool Card Rewriter (Critical!):**
  * Strip strict JSON Schema validators (`format: "email"`, `format: "uri"`, `pattern` on string params) and append `"Placeholders such as [EMAIL_1] or [PERSON_1] are accepted."` to descriptions so cloud LLMs never choke on placeholders.
  * Attach effect label (`read`, `local_write`, `external`), look-alike disambiguation notes (`"searches local notes only, not email"`), and configured `relations` hints (`mail_drafts.create_draft` → `contacts.lookup_email`).
* [ ] **B2.4 Tests (`tests/test_discovery.py`):** Recall test on hospital-bill query, schema relaxation test (`format: email` stripped), token-savings calculation test.

### Block B3: Policy Engine & Out-of-Band Approval Manager (`src/cloakroom/policy/`) — ~2.5 Hours
* [ ] **B3.1 Effect Classifier:** Resolve effect class in strict priority order: (1) user config override, (2) MCP tool annotations (`readOnlyHint`, `destructiveHint`, `openWorldHint`), (3) fail-safe default `UNKNOWN` (treated identically to `EXTERNAL`).
* [ ] **B3.2 `ApprovalManager` (Implements `ApprovalResolverProtocol`):**
  * Compute canonical SHA-256 hash of `(tool_id, restored_arguments)`.
  * Generate risk flags: check recipient emails against known contacts (`"UNKNOWN_RECIPIENT"`), check `RestoreResult.contains_identifier_tier` (`"IDENTIFIER_EXPOSURE: [ACCT_1], ..."`).
  * Create `PendingApproval` holding an `asyncio.Event`, publish `approval_requested` event to `EventBusProtocol`. **Split the two clocks (INTERFACE.md — they are separate):** the `invoke_tool` call waits up to **30 s (spec default)** for a decision; with none arriving, return `pending_approval` + `approval_id` (deferred execution) while the approval stays open. The approval's **expiry** — separate from the wait — defaults to **120 s for live demos** (spec example: 300 s). Final outcome is fetched by the host via `inspect_status(approval_id)`.
  * On `resolve(approval_id, approved, payload_hash)`: verify hash matches exactly (mismatch → deny), update status, set event, emit `approval_resolved`. On expiry, mark `EXPIRED` and deny fail-closed. The gateway — never the host — executes the approved payload and retains the cloaked result for `inspect_status`.
* [ ] **B3.3 Tests (`tests/test_policy.py`):** Auto-allow `read`/`local_write`, block `external`/`unknown`, payload hash mismatch rejection, unknown recipient flag detection, timeout denial.

### Block B4: MCP Gateway, CLI `serve` & Fallback Replay Driver (`src/cloakroom/gateway/`, `cli.py`, `demo/`) — ~4.5 Hours
* [ ] **B4.1 Downstream `ClientPool`:** Spawn configured downstream stdio MCP servers via `mcp.client.stdio`, handle startup errors gracefully, collect tool schemas into `Discovery`, and route `call_tool`.
* [ ] **B4.2 Front Stdio MCP Server:** Expose exactly 3 meta-tools via `mcp.server`:
  * `discover_tools(query: str, max_tools: int = 6)`
  * `invoke_tool(tool_id: str, arguments: dict[str, Any])`
  * `inspect_status(approval_id: str | None = None)`
  * **Pipeline inside `invoke_tool`:** validate `tool_id` → call `CloakEngineProtocol.restore(arguments)`; **if `blocked=True`, return the host-facing error listing valid placeholder TYPES (never values) and STOP — no downstream call** → classify effect → if `external`/`unknown`, await `ApprovalManager` (**30 s wait → return `pending_approval` + `approval_id`; outcome retrieved later via `inspect_status`**; only execute after an approved decision, hash-matched) → forward restored args to `ClientPool` → pass downstream result (and any error text!) through `CloakEngineProtocol.cloak(...)` → publish `GatewayEvent` (cloaked only — no raw payloads on the bus) → return strictly `cloaked_payload` to host.
  * **Zero Stdout Pollution:** Assert logging goes strictly to `stderr` or `cloakroom.log`.
* [ ] **B4.3 `cloakroom serve` CLI (`src/cloakroom/cli.py`):** Load config via existing `configuration/loader.py`, start embedded Control Room Uvicorn task in the same `asyncio` loop **via Dev A's `create_control_room(event_bus, approvals, token)` exactly as signed in `contracts.py`**, print the `http://127.0.0.1:<port>/?token=<secret>` URL to **`stderr`**, and run stdio MCP loop.
* [ ] **B4.4 Offline Fallback Driver (`demo/replay_agent.py`) & Demo Configs:** Write a standalone script that connects as an MCP stdio client to the **real** `cloakroom serve` process and replays the exact 4-minute demo steps (discover → read bill/bank/insurance/contacts → create draft → trigger external audit send [pause for live Deny] → trigger legitimate send [pause for live Approve]) with 1.5s pacing. Guarantees a 100% live demo even if Wi-Fi or Anthropic API fails.
* [ ] **B4.5 Tests (`tests/test_gateway_e2e.py`):** End-to-end test using dummy `CloakEngineProtocol` (before merge) and real `Vault`/`CloakPipeline` (after merge), asserting zero raw PII returns to host and zero unauthorized external sends execute.

---

## 6. Integration Checkpoints & Merge Protocol

| Checkpoint | Timing | Action | Exit Criteria |
| --- | --- | --- | --- |
| **Sync 0** | T + 15 min | Commit `pyproject.toml`, `uv.lock`, and `src/cloakroom/contracts.py` to `main`. | CI green on `main`; both devs branch off. |
| **Sync 1** | End of Block 2 (~7 hrs) | 10-min check-in: confirm neither dev needed any change to `contracts.py`. | `tests/test_vault.py`, `test_cloak.py`, `test_discovery.py`, `test_paperwork_pack.py` all green on respective branches. |
| **Sync 2 (Merge)** | End of Block 3 (~11 hrs) | Merge `feat/dev-a-privacy-ui` → `main`, then merge `feat/dev-b-mcp-runtime` → `main`. Dev B swaps stubs in `gateway/app.py` for Dev A's real `Vault`, `CloakPipeline`, and `ControlRoom`. | Full `replay_agent.py` drives real gateway + live Control Room browser UI with Approve/Deny working. |
| **Sync 3 (Freeze)** | T - 3 hrs before pitch | Test in Claude Desktop cold-start 3 times, run `benchmarks/run_eval.py`, record 3-min HD backup video, paste real numbers into `README.md` & slides. | Feature freeze. Only bug fixes allowed. |

---

## 7. Copy-Paste Starting Prompts for Coding IDEs

### Prompt for Phase 0 (Run Once Together on `main`)

```text
You are helping set up Phase 0 of a two-developer hackathon MVP for Cloakroom (a local privacy & approval MCP gateway in Python 3.11+).

Before making any edits, inspect:
1. README.md
2. pyproject.toml
3. src/cloakroom/configuration/models.py and loader.py
4. Existing tests and CI configuration (.github/workflows/*)

Your ONLY Phase 0 tasks on `main` are:
1. Ensure pyproject.toml has the minimal MVP runtime dependencies needed (mcp, fastapi, uvicorn, cryptography, rank-bm25, and a cross-platform Aho-Corasick library such as ahocorasick-rs or pyahocorasick—verify it installs cleanly without breaking Windows/Ubuntu Python 3.11-3.14 CI, plus httpx in dev deps). Run `uv lock` and `uv sync`.
2. Create `src/cloakroom/contracts.py` defining the shared cross-module dataclasses, enums, and Protocols:
   - EffectClass (READ, LOCAL_WRITE, EXTERNAL, UNKNOWN)
   - ApprovalStatus (PENDING, APPROVED, DENIED, EXPIRED)
   - CloakedEntity, CloakResult, RestoreResult, CatalogMetrics, ApprovalRequest, GatewayEvent
   - CloakEngineProtocol, ApprovalResolverProtocol, EventBusProtocol
3. Keep all existing tests, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src`, and `uv run pytest` 100% green.

Do NOT implement any business logic in vault/, cloak/, discovery/, policy/, gateway/, or controlroom/ yet. Keep this commit small, clean, and strictly typed.
```

---

### Dev A — Coding IDE Starting Prompt

```text
You are Dev A working on the Cloakroom hackathon MVP on branch `feat/dev-a-privacy-ui`.

FIRST, read these existing files to match the repository's exact conventions, config models, error types, and architecture:
- README.md
- docs/ARCHITECTURE.md, docs/INTERFACE.md, docs/CONFIGURATION.md, docs/THREAT_MODEL.md
- src/cloakroom/contracts.py
- src/cloakroom/configuration/models.py and loader.py
- src/cloakroom/errors* and src/cloakroom/observability* (whatever currently exists)

STRICT FILE OWNERSHIP (ZERO MERGE CONFLICT RULE):
You may ONLY create or edit files inside:
- src/cloakroom/vault/
- src/cloakroom/cloak/
- src/cloakroom/controlroom/
- benchmarks/
- tests/test_vault.py, tests/test_cloak.py, tests/test_controlroom.py

NEVER edit pyproject.toml, uv.lock, src/cloakroom/contracts.py, src/cloakroom/cli.py, src/cloakroom/gateway/, src/cloakroom/discovery/, src/cloakroom/policy/, or the Paperwork Pack server folders. Dev B owns those in parallel.

ENGINEERING & CI CONSTRAINTS:
- Python 3.11+ strict typing (`uv run mypy src` must pass cleanly).
- Formatting & lint (`uv run ruff check .` and `uv run ruff format --check .` must pass).
- Cross-platform Windows + Ubuntu compatibility: always use `pathlib.Path` and explicit `encoding="utf-8"`.
- CRITICAL MCP SAFETY: Never call `print()` to stdout anywhere in runtime code. Configure Uvicorn so zero logs ever write to stdout (use stderr or disable access logs).
- Implement against the Protocols and dataclasses in `src/cloakroom/contracts.py`.

YOUR IMPLEMENTATION ORDER (build and verify each block with pytest before moving on):
1. `src/cloakroom/vault/`:
   - Canonicalizer (whitespace, case, honorifics, digit separators, gazetteer alias mapping — no fuzzy merging).
   - Persistent SQLite vault with AES-256-GCM encryption + keyed HMAC-SHA256 lookup hash, backed by an auto-generated local keyfile (0600 permissions; do NOT block on OS keychain GUI prompts).
   - Stable typed placeholders (`[PERSON_1]`, `[MED_ID_1]`, `[ACCT_1]`, `[EMAIL_1]`, `[ORG_1]`, `[PHONE_1]`, `[GOVID_1]`, `[ADDR_1]`, `[SECRET_1]`).
   - Write comprehensive tests in `tests/test_vault.py`.

2. `src/cloakroom/cloak/`:
   - Implement `CloakEngineProtocol` with the 6-stage pipeline:
     (1) Content filter (withhold binary/image blocks),
     (2) Field policy (mask configured structured keys deterministically),
     (3) Gazetteer sweep (longest-non-overlapping multi-pattern match; protect already-minted `[TYPE_N]` spans),
     (4) Detectors with checksum validation (Aadhaar Verhoeff, card Luhn, PAN, IFSC, email, phone, UHID/medical IDs, API keys, custom config patterns; keep Analytical amounts/dates visible by default),
     (5) Vault mint/reuse,
     (6) Fail-closed Tripwire (rescan cloaked output against all vault/gazetteer real values; re-cloak once; withhold on second hit).
   - Implement `restore(arguments)` per the frozen contract: for invented/unknown placeholders set `blocked=True` + `unknown_placeholders` (token strings only — never values) and leave them unrestored; restore known placeholders locally; compute `contains_identifier_tier`. (Dev B's gateway turns `blocked=True` into the host-facing error listing valid placeholder **types**.)
   - Write comprehensive tests in `tests/test_cloak.py` including the README hospital bill, bank export, and error-message cloaking cases.

3. `src/cloakroom/controlroom/`:
   - Implement `EventBusProtocol` (`asyncio.Queue` fan-out + rolling history + SQLite audit log).
   - Embedded FastAPI + Uvicorn app bound strictly to `127.0.0.1` with a per-launch random token (`secrets.token_urlsafe(24)`).
   - Endpoints: `GET /` (single-file dark-mode HTML/CSS/JS UI), `GET /api/events` (SSE), `GET /api/state`, `POST /api/approvals/{id}/decision`.
   - UI must look like a polished developer security console (not plain HTML):
     * Top Command Bar: `127.0.0.1` live badge, Catalog Meter (`exposed / total tools + % tokens saved`), Leak/Cloaked counters, global "Reveal Local Values" toggle (OFF/blurred by default).
     * Main 2-pane workspace: Left = Live 2-column diff feed (`Laptop Saw` vs `Cloud Saw`, color-coded `[TYPE_N]` pills, effect badge, latency ms, Tripwire PASS badge); Right = Pending Approvals queue showing real recipient, real body with identifier highlights, red risk flags (`UNKNOWN_RECIPIENT`, `IDENTIFIER_EXPOSURE`), SHA-256 hash badge, and Approve/Deny buttons.
     * Secondary tab: Vault summary + Audit log table + Export JSON.
   - Include a tiny standalone preview script (`src/cloakroom/controlroom/dev_preview.py`) with mocked events so we can run and inspect the UI without waiting for Dev B.
   - Write tests in `tests/test_controlroom.py`.

4. `benchmarks/run_eval.py`:
   - Automated benchmark measuring leak rate (with/without gazetteer), p50/p95 cloak latency, and placeholders for control/discovery metrics once merged.

Start now by inspecting the repository and proposing your exact file list for Block 1 (`vault/`), then begin implementing Block 1.
```

---

### Dev B — Coding IDE Starting Prompt

```text
You are Dev B working on the Cloakroom hackathon MVP on branch `feat/dev-b-mcp-runtime`.

FIRST, read these existing files to match the repository's exact conventions, config models, error types, and architecture:
- README.md
- docs/ARCHITECTURE.md, docs/INTERFACE.md, docs/CONFIGURATION.md, docs/THREAT_MODEL.md
- src/cloakroom/contracts.py
- src/cloakroom/configuration/models.py and loader.py
- src/cloakroom/cli.py
- Existing Paperwork Pack server folders (currently containing `.gitkeep`)

STRICT FILE OWNERSHIP (ZERO MERGE CONFLICT RULE):
You may ONLY create or edit files inside:
- Paperwork Pack server folders (documents, bank, contacts, mail_drafts, notes)
- demo_data/, demo/, config/demo.*
- src/cloakroom/discovery/
- src/cloakroom/policy/
- src/cloakroom/gateway/
- src/cloakroom/cli.py
- tests/test_paperwork_pack.py, tests/test_discovery.py, tests/test_policy.py, tests/test_gateway_e2e.py

NEVER edit pyproject.toml, uv.lock, src/cloakroom/contracts.py, src/cloakroom/vault/, src/cloakroom/cloak/, src/cloakroom/controlroom/, or benchmarks/. Dev A owns those in parallel.
Until merge, use lightweight in-memory test doubles implementing `CloakEngineProtocol` and `EventBusProtocol` from `src/cloakroom/contracts.py` inside your tests/bootstrap so your code compiles and passes all tests independently.

ENGINEERING & CI CONSTRAINTS:
- Python 3.11+ strict typing (`uv run mypy src` must pass cleanly).
- Formatting & lint (`uv run ruff check .` and `uv run ruff format --check .` must pass).
- Cross-platform Windows + Ubuntu compatibility: always use `pathlib.Path` and explicit `encoding="utf-8"`.
- CRITICAL MCP STDIO RULE: The gateway communicates with Claude Desktop over stdout JSON-RPC. NEVER call `print()` to stdout anywhere in gateway, discovery, policy, or Paperwork Pack servers. All logs and the Control Room URL MUST go to `stderr` or a log file.

YOUR IMPLEMENTATION ORDER (build and verify each block with pytest before moving on):
1. `demo_data/` + Paperwork Pack Local MCP Servers:
   - Create consistent synthetic files for Aarav Sharma:
     * Hospital bill (`Lakeview Hospital`, UHID `LH-99214`, `Rs 48,500`, `billing@lakeview.example`, plus an external audit verification footer pointing to `verify-refund@external-audit.example` so Demo Beat 3 reliably triggers Unknown Recipient + Identifier Exposure).
     * Bank statement CSV (account `4401928371`, debit `Rs 52,000` to `Lakeview Hospital` — exact Rs 3,500 discrepancy — plus filler rows).
     * Insurance policy note covering billing overcharges > Rs 2,000.
     * Contacts JSON containing `billing@lakeview.example` and Aarav's profile/aliases, deliberately omitting `verify-refund@external-audit.example`.
   - Build lightweight `FastMCP` stdio servers for `documents`, `bank`, `contacts`, `mail_drafts` (`create_draft` writes to local `drafts/`, `send_draft` writes to local `outbox/` so no SMTP/OAuth is needed), and `notes` (+ extra utility read tools so the indexed catalog has 20+ tools to make Catalog Meter savings vivid).
   - Write tests in `tests/test_paperwork_pack.py`.

2. `src/cloakroom/discovery/`:
   - In-memory tool catalog indexing all downstream servers + approximate schema token calculator.
   - Fast BM25 retrieval (`rank-bm25`) with lightweight domain synonym expansion (`bill`/`invoice`, `mail`/`email`, `bank`/`transaction`) so startup is < 200ms offline.
   - Tool-card schema relaxation: strip strict string validators like `format: "email"` and append `"Placeholders like [EMAIL_1] are accepted."` to parameter descriptions; attach effect class labels, look-alike disambiguation notes, and relation hints.
   - Write tests in `tests/test_discovery.py`.

3. `src/cloakroom/policy/`:
   - Effect classifier: config override > MCP tool annotations > default `UNKNOWN` (treated as `EXTERNAL`).
   - Implement `ApprovalResolverProtocol` (`ApprovalManager`): canonical SHA-256 hash of `(tool_id, restored_arguments)`, risk flags (`UNKNOWN_RECIPIENT` checked against contacts, `IDENTIFIER_EXPOSURE` from `RestoreResult`), `asyncio.Event` awaiting user decision with split clocks — 30 s `invoke_tool` wait (then `pending_approval`, outcome via `inspect_status`) vs separate approval expiry (120 s demo default, expiring fail-closed as `DENIED`/`EXPIRED`), and event emission via `EventBusProtocol`.
   - Write tests in `tests/test_policy.py`.

4. `src/cloakroom/gateway/`, `src/cloakroom/cli.py`, and `demo/replay_agent.py`:
   - `ClientPool` managing downstream stdio MCP sessions and tool invocation.
   - Front stdio MCP server exposing exactly 3 meta-tools: `discover_tools`, `invoke_tool`, `inspect_status`.
   - Full `invoke_tool` pipeline: validate tool -> `cloak_engine.restore(args)` (if `blocked=True`: return host-facing error listing placeholder TYPES, stop — no downstream call) -> policy & approval gate (30 s wait -> return `pending_approval` + `approval_id`; outcome later via `inspect_status`; execute only after hash-matched approval) -> downstream call -> `cloak_engine.cloak(result_or_error)` -> emit `GatewayEvent` (cloaked only — no raw payloads on the bus) -> return only cloaked payload.
   - Wire `cloakroom serve` in `src/cloakroom/cli.py` (with clean dependency injection so swapping in Dev A's `Vault`, `CloakPipeline`, and `ControlRoom` takes ~20 lines at merge time).
   - Create `config/demo.servers.yaml`, `config/demo.gazetteer.yaml`, `config/demo.privacy_policy.yaml`.
   - Create `demo/replay_agent.py`: a scripted offline MCP client that connects to the real `cloakroom serve` gateway and replays the full hospital-bill + draft + external-audit-send (Deny) + legitimate-send (Approve) demo cleanly without internet access.
   - Write integration tests in `tests/test_gateway_e2e.py`.

Start now by inspecting the repository and proposing your exact file list for Block 1 (`demo_data/` + Paperwork Pack servers), then begin implementing Block 1.
```
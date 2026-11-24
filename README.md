# Cloakroom

A local gateway that lets a cloud AI assistant work with your personal files and apps while your private details stay on your laptop.

Built for the Make MCP Matter track (Less Magic, More Utility).

## Contents

- [Overview](#overview)
- [Concepts](#concepts)
- [How it works](#how-it-works)
- [Worked example](#worked-example)
- [Architecture](#architecture)
- [Privacy model](#privacy-model)
- [Control Room](#control-room)
- [Paperwork Pack](#paperwork-pack)
- [Threat model and limitations](#threat-model-and-limitations)
- [Testing and evaluation](#testing-and-evaluation)
- [Technology](#technology)
- [Repository layout](#repository-layout)
- [Related work](#related-work)
- [Installation and usage](#installation-and-usage)
- [Security, license and acknowledgements](#security-license-and-acknowledgements)

## Overview

### Problem

Some of the most useful things an AI assistant can do involve a person's most sensitive records. Checking a hospital bill against a bank statement, comparing the difference with an insurance policy and drafting a dispute email touches names, account numbers, medical identifiers and money in a single task.

The Model Context Protocol (MCP) lets an assistant read local files and use apps, which makes that task possible. The default setup brings three problems with it.

- **Leak.** Every tool result goes to a cloud model and to whatever logging surrounds it. A bill read through MCP arrives with the patient's name, record number and bank account intact.
- **Uncontrolled action.** The connection that reads can also send, share or delete, usually under one blanket permission. Text the assistant reads, such as a PDF or an email, can try to steer what it does next.
- **Overload.** Each connected server adds tool definitions to every request. With enough servers the model carries hundreds of them, which costs tokens and makes a wrong tool choice more likely.

So people either skip the connection and do the paperwork by hand, or connect everything and hope.

### Approach

Cloakroom is a gateway process that runs on the user's machine. The assistant's host application (Claude Desktop, for example) connects to it as if it were one MCP server. Cloakroom in turn connects to the user's real MCP servers. Nothing reaches the assistant, and nothing it does reaches an app, except through Cloakroom.

The design rests on one rule: the assistant does the thinking, and deterministic code guards the doors. Whether a value is private, whether it may be restored and whether an action needs approval are decided by rules that can be read, tested and audited. No language model takes part in those decisions.

The name describes the mechanism. You leave your coat (your identity) at the door, the assistant receives a numbered ticket such as `[PERSON_1]`, and the coat is handed back only to places you have allowed.

### Design goals

| Goal | Meaning | Main mechanisms |
| --- | --- | --- |
| Private details stay local | Real values do not cross the boundary to the cloud model | Gazetteer, detectors, vault, tripwire |
| Nothing leaves without approval | Actions that send, share, delete or are unrecognised wait for the user | Effect classes, out-of-band approval |
| The assistant sees only the tools it needs | Tools are found on demand instead of listed up front | Three meta-tools, hybrid retrieval |

These goals hold within the scope below. Section [Threat model and limitations](#threat-model-and-limitations) lists what falls outside it.

### Scope and non-goals

In scope:

- Data that apps return to the assistant (tool results, errors and tool descriptions).
- Actions the assistant requests (tool calls).
- A single user on a single machine.

Out of scope:

- Text the user types into the chat themselves. Cloakroom cannot see it.
- Images and scanned documents. They are withheld, not read.
- The behaviour of the downstream servers. A server the user installs is trusted to do what its code does.
- Anonymity and regulatory compliance. Pseudonymisation lowers exposure and gives neither.

## Concepts

| Term | Meaning |
| --- | --- |
| Host | The application the user chats in, such as Claude Desktop. It talks to the cloud model. |
| Downstream server | An MCP server for an app or data source: files, bank CSV, contacts, mail. Cloakroom is its client. |
| Placeholder | A stand-in for a real value, written `[TYPE_N]`, for example `[PERSON_1]` or `[ACCT_2]`. |
| Cloak | The pipeline that replaces private values with placeholders before data goes to the host. |
| Restore | Replacing placeholders with real values locally, just before a call reaches a downstream server. |
| Vault | The encrypted local store mapping placeholders to real values. |
| Gazetteer | A list of values known to be private to this user: their names, aliases, contacts, addresses. Built from the user's own data. |
| Tripwire | A final scan of outgoing data for any real value the vault or gazetteer knows. |
| Effect class | A label for what a tool can do: `read`, `local_write`, `external` or `unknown`. |
| Approval card | A prompt in the Control Room showing the real details of an action that needs the user's decision. |
| Control Room | The local dashboard: live view of traffic, approvals, vault and policy controls. |
| Paperwork Pack | Ready-made local MCP servers for documents, bank data, contacts, notes and mail drafts. |

## How it works

### Request lifecycle

The sequence below follows one read and one outward action.

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant H as Host and cloud model
    participant C as Cloakroom
    participant S as Downstream servers
    participant R as Control Room

    H->>C: discover_tools(query)
    C-->>H: about six tool cards
    H->>C: invoke_tool(read tool, arguments)
    C->>S: call with restored values
    S-->>C: raw result
    C->>C: cloak and run tripwire
    C-->>H: result with placeholders
    H->>C: invoke_tool(external tool, arguments)
    C->>R: approval card with real values
    U->>R: approve or deny
    C->>S: call with approved payload
    S-->>C: raw result
    C-->>H: cloaked result or denial
```

### Meta-tools

The host sees three tools and nothing else. Every downstream tool is reached through them.

| Tool | Parameters | Purpose |
| --- | --- | --- |
| `discover_tools` | `query`, `max_tools` (default 6) | Returns tool cards for the best matches |
| `invoke_tool` | `tool_id`, `arguments` | Runs a downstream tool through the full pipeline |
| `inspect_status` | `approval_id` (optional) | Reports gateway status and the outcome of a pending approval |

```json
{
  "name": "discover_tools",
  "description": "Find the tools needed for a task. Call this first. Values such as [PERSON_1] are stand-ins for private data; pass them back exactly as written.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "query": { "type": "string" },
      "max_tools": { "type": "integer", "default": 6, "minimum": 1, "maximum": 15 }
    },
    "required": ["query"]
  }
}
```

The usage rules live in the tool descriptions, because descriptions are delivered on every protocol revision. Cloakroom relies only on `tools/list` and `tools/call`, which every MCP revision supports. It does not depend on newer features such as multi round-trip requests, because host support cannot be assumed. The full reference is in [docs/INTERFACE.md](docs/INTERFACE.md).

### Discovery

#### Indexing

At startup the gateway connects to each configured server as an MCP client, lists its tools and builds a catalog in memory. Each entry holds the tool name, description, parameter schema, effect class and an embedding of its text.

#### Retrieval

Two rankings are combined. BM25 over the tool text catches exact vocabulary. Embeddings from `all-MiniLM-L6-v2`, a model of roughly 90 MB that runs on CPU, catch paraphrase, so a request about a "bill" still finds a tool described as handling "invoices". Reciprocal rank fusion merges the two lists. A cross-encoder reranker was considered and left out to keep latency and dependencies down.

#### Tool cards

The cards returned to the host are not copies of the downstream definitions. Four things change.

- Parameters that may receive placeholders lose constraints such as `format: email`, and their descriptions say a placeholder is acceptable. Without this a model may refuse to put `[EMAIL_1]` into an email field.
- Each card carries its effect label.
- Look-alike tools, found by embedding similarity at index time, carry a short note, for example "searches local notes only, not email".
- A small `relations` map in configuration adds hints such as "`mail_drafts.create_draft` usually needs `contacts.lookup_email`". If the model still misses a step, it calls `discover_tools` again.

Example output (illustrative):

```json
{
  "tools": [
    {
      "tool_id": "bank.query_transactions",
      "effect": "read",
      "description": "Query bank transactions by amount, date or payee."
    },
    {
      "tool_id": "notes.search_notes",
      "effect": "read",
      "description": "Search local notes.",
      "note": "Searches local notes only, not email."
    }
  ],
  "hints": ["mail_drafts.create_draft usually needs contacts.lookup_email"],
  "catalog": { "exposed": 6, "total": 41 }
}
```

Token counts shown in the Control Room are approximate. They use a stand-in tokenizer, not the assistant's own.

### Cloak pipeline

Everything that goes up to the host passes through the same pipeline: tool results, error messages and tool descriptions. Errors are included because downstream servers often echo file paths and names in them.

```mermaid
flowchart TD
    A["Payload from a downstream server"] --> B{"Content type"}
    B -->|"text or JSON"| C["Field policy"]
    B -->|"image or binary"| B2["Replace block with a withheld notice"]
    B2 --> C
    C --> D["Gazetteer sweep"]
    D --> E["Detectors"]
    E --> F["Vault: mint or reuse placeholders"]
    F --> G["Tripwire: rescan for known real values"]
    G -->|"clean"| H["Send to host"]
    G -->|"hit"| I["Re-cloak once"]
    I --> J{"Still a hit?"}
    J -->|"no"| H
    J -->|"yes"| W["Withhold the whole payload"]
    X["Any stage raises an error"] --> W
```

| Stage | Behaviour | Why it exists |
| --- | --- | --- |
| Content filter | Text and JSON pass. Images and binary blocks are replaced by a notice. | Pixels cannot be scrubbed, so scanned pages never reach the host. |
| Field policy | Named fields on configured servers (`account_no`, `patient_name`, `email`) are always masked. | Deterministic for structured data, with no detection step to miss anything. |
| Gazetteer sweep | Aho-Corasick matching of every known value and alias over every string in the payload. | Catches nicknames, contacts and addresses that name-recognition models miss. |
| Detectors | Patterns with validation: Aadhaar (Verhoeff), card numbers (Luhn), PAN, IFSC, phone, email, API keys, and custom patterns from configuration. | Finds identifiers the user never listed. Checksums cut false positives. |
| Vault | Mints a placeholder for each new value and reuses the existing one for a known value. | One entity gets one placeholder everywhere. |
| Tripwire | Rescans the output against every real value in the vault and gazetteer. A hit is re-cloaked once. A second hit withholds the payload. | Turns best-effort scrubbing into a checked result. |

### Vault

The vault maps real values to placeholders. Placeholders are typed (`PERSON`, `ORG`, `EMAIL`, `PHONE`, `ACCT`, `GOVID`, `MED_ID`, `ADDR`, `SECRET`) and numbered per type.

- **Stable across tools and chats.** The same person is `[PERSON_1]` in the bill, the bank export and the insurance note, and in next week's conversation.
- **Canonical matching.** Values are normalised before lookup (case, whitespace, honorifics, separators in digit strings), and the gazetteer's alias table maps variants of one person to one entity. Names are not merged by fuzzy matching. A wrong merge restores the wrong person, while a duplicate placeholder does no harm.
- **Persistent and encrypted.** The vault is an SQLite file. Values are encrypted with AES-256-GCM, the key sits in the operating system keychain, and lookups use a keyed hash. It persists because chats outlive gateway restarts, and a placeholder in an old chat must still resolve.
- **User controls.** Wipe clears the vault. Rotate starts a new numbering. Stable placeholders let a cloud provider link two conversations that mention the same one, and rotation is the remedy.

The bracket format `[TYPE_N]` is deliberate. Chat interfaces can treat angle brackets as HTML and hide them. The format is checked in the target host before it is fixed.

```sql
CREATE TABLE entities (
    token       TEXT PRIMARY KEY,      -- for example [PERSON_1]
    entity_type TEXT NOT NULL,
    keyed_hash  BLOB NOT NULL UNIQUE,  -- HMAC-SHA256 of the canonical value
    ciphertext  BLOB NOT NULL,         -- AES-256-GCM
    nonce       BLOB NOT NULL,
    first_seen  TEXT NOT NULL,         -- tool that first produced the value
    hits        INTEGER NOT NULL DEFAULT 1
);
```

### Restoring values

For every `invoke_tool` call the gateway does the following.

1. Checks that `tool_id` exists in the catalog.
2. Scans every string in `arguments` for placeholders. An unknown placeholder, such as one the model invented, stops the call. The error lists valid placeholder types, never values, so the model can correct itself.
3. Looks up the tool's effect class and applies the rules below. Restoration into a tool that sends data outside the machine happens only after approval.
4. Replaces placeholders with real values locally and forwards the call.
5. Passes the response through the cloak pipeline.

Restoration is gated because it is also an attack path. If text in a document steers the assistant into asking for an email to a stranger with your account number in the body, an ungated gateway would fill in the real number. The effect rules and the approval step exist to prevent that.

### Effects and approvals

#### Effect classes

| Class | Meaning | Behaviour |
| --- | --- | --- |
| `read` | No side effects | Runs automatically |
| `local_write` | Changes local state only, such as creating a draft or saving a note | Runs automatically and is logged |
| `external` | Sends, shares, uploads, posts or deletes | Needs approval |
| `unknown` | No usable information | Treated as `external` |

A tool's class comes from, in priority order, the user's configuration override, the server's tool annotations (`readOnlyHint`, `destructiveHint`, `openWorldHint`), and the default. Annotations are hints published by the server, not guarantees. A tool without them falls to `unknown` and asks for approval.

#### Approval flow

Approval happens in the Control Room, never in the chat. If it travelled through the assistant's channel, a manipulated assistant could answer for the user.

```mermaid
flowchart TD
    A["invoke_tool call"] --> B{"Tool in catalog?"}
    B -->|"no"| E1["Error: unknown tool"]
    B -->|"yes"| C{"Unknown placeholder?"}
    C -->|"yes"| E2["Error: list valid placeholder types"]
    C -->|"no"| D{"Effect class"}
    D -->|"read"| R["Restore, call, cloak result"]
    D -->|"local_write"| L["Restore, call, log, cloak result"]
    D -->|"external or unknown"| P["Build approval card with real values"]
    P --> Q{"Decision within 30 s?"}
    Q -->|"approve"| X["Call with approved payload, cloak result"]
    Q -->|"deny or expire"| Y["Return denied"]
    Q -->|"no decision yet"| Z["Return pending_approval with an id"]
```

The approval card shows the tool, the real recipient and body, and a flag when the recipient is not in the user's contacts. It highlights any value from the identifier tier that the action would send. The approval is bound to a hash of the exact payload shown, so arguments cannot change after the user clicks.

```json
{
  "approval_id": "ap_0192",
  "tool_id": "mail_drafts.send_draft",
  "effect": "external",
  "recipient": { "value": "billing@lakeview.example", "in_contacts": true },
  "identifier_tier_values": ["account number"],
  "payload_sha256": "9c1f...e47a",
  "expires_in_s": 300
}
```

Hosts may time out long calls, so `invoke_tool` waits about 30 seconds for a decision and then returns `pending_approval`. After the user approves, the gateway runs the call itself and keeps the cloaked result. The assistant retrieves it with `inspect_status(approval_id)`. An approval nobody answers expires as a denial.

In the default workflow the assistant never sends mail. It creates a draft, which is a `local_write`, and the user sends it from their mail client.

### Failure behaviour

The gateway fails closed. When something goes wrong, data is withheld and raw values are never the fallback.

| Condition | Behaviour |
| --- | --- |
| A cloak stage raises an error | Payload withheld; the host receives a withheld notice |
| Tripwire still hits after re-cloaking | Payload withheld |
| Unknown placeholder in arguments | Call rejected; error lists valid placeholder types |
| Unknown `tool_id` | Call rejected with the closest matching ids |
| Tool with no effect information | Treated as `external` and needs approval |
| Approval not answered before expiry | Treated as denied |
| Downstream server times out or crashes | Error returned; writes are not retried |
| Image or binary content | Replaced by a notice |

## Worked example

The task, typed without any personal detail:

> Check my latest hospital bill against my bank statement, see whether my insurance notes cover the difference, and draft a dispute email.

All data in this example is synthetic.

| Step | What happens |
| --- | --- |
| 1 | The assistant calls `discover_tools`. Cloakroom returns six tool cards out of the full catalog, with a note that notes search and mail search are different tools. |
| 2 | `documents.read_text` returns the bill. The names, record number and contact are cloaked. |
| 3 | `bank.query_transactions` returns a payment of Rs 52,000. The patient is again `[PERSON_1]`. |
| 4 | The assistant compares Rs 48,500 with Rs 52,000 and finds a Rs 3,500 difference. Amounts are visible by default so it can do this arithmetic. |
| 5 | `notes.search_notes` returns the insurance clause. The assistant checks whether it covers the amount. |
| 6 | `contacts.lookup_email` returns `[EMAIL_1]` for the hospital billing address. |
| 7 | `mail_drafts.create_draft` is called with placeholders. Cloakroom restores the real values and the draft appears in the user's drafts. |
| 8 | The Control Room shows every step as two panes: what the cloud saw, and what the laptop saw. |

What the downstream server returns for the bill:

```text
Patient: Aarav Sharma    UHID: LH-99214
Hospital: Lakeview Hospital
Total billed: Rs 48,500
Billing contact: billing@lakeview.example
```

What the assistant receives:

```text
Patient: [PERSON_1]    UHID: [MED_ID_1]
Hospital: [ORG_1]
Total billed: Rs 48,500
Billing contact: [EMAIL_1]
```

What the assistant sends to create the draft, and what the mail server finally receives:

```json
{
  "tool_id": "mail_drafts.create_draft",
  "arguments": {
    "to": "[EMAIL_1]",
    "subject": "Billing discrepancy for [PERSON_1]",
    "body": "Dear [ORG_1] billing team, the bill for [PERSON_1] (record [MED_ID_1]) shows Rs 48,500. Account [ACCT_1] was charged Rs 52,000. Please explain the Rs 3,500 difference."
  }
}
```

```json
{
  "to": "billing@lakeview.example",
  "subject": "Billing discrepancy for Aarav Sharma",
  "body": "Dear Lakeview Hospital billing team, the bill for Aarav Sharma (record LH-99214) shows Rs 48,500. Account 4401928371 was charged Rs 52,000. Please explain the Rs 3,500 difference."
}
```

## Architecture

![Cloakroom architecture diagram](docs/diagrams/architecture.png)

The diagram source is kept in `docs/diagrams/architecture.puml`. It shows the cloud model and host on the outside, the Cloakroom gateway on the user's machine with its discovery, policy, cloak and vault components, the downstream servers behind it, and the Control Room beside it on a separate local channel.

### Trust zones

| Zone | Contents | Trust |
| --- | --- | --- |
| Cloud | The model provider and anything between the host and it | Untrusted. Sees placeholders only. |
| Gateway | Cloakroom's discovery, policy, cloak, vault and Control Room | Trusted. Deterministic code, no language model. |
| Downstream servers | Servers the user installed | Trusted to do what their code does. Not audited by Cloakroom. |
| User channel | The Control Room approval cards | Trusted. Not reachable by the assistant. |

### Components

| Component | Responsibility |
| --- | --- |
| Front | MCP server over stdio exposing the three meta-tools to the host |
| Client pool | MCP clients for each downstream server, with lifecycle handling |
| Discovery | Catalog, hybrid retrieval, tool card construction |
| Policy engine | Effect classes, restoration rules, approval decisions |
| Cloak pipeline | Content filter, field policy, gazetteer, detectors, tripwire |
| Vault | Placeholder mapping, encryption, wipe and rotate |
| Event bus | Emits an event for every step to the audit log and the Control Room |
| Control Room | Local web interface for live view, approvals and settings |

The gateway runs as a stdio MCP server started by the host, which is how Claude Desktop launches local servers. The Control Room runs inside the same process on the loopback interface and requires a random per-launch token, so other local processes and the assistant have no route to the approval endpoint.

### Stored data

| Store | Contents | Protection |
| --- | --- | --- |
| Vault | Entity type, counter, keyed hash, ciphertext, nonce | AES-256-GCM, key in the OS keychain |
| Catalog | Tool id, server, schema, effect class, embedding | Local file, no personal data |
| Approvals | Approval id, payload hash, status, timestamps | The displayed payload is held in memory until decided |
| Audit log | Time, tool, effect class, entity counts, timings, the cloud-view payload | Real values are never written. The local view is rebuilt from the vault on display. |

## Privacy model

### Tiers

| Tier | Examples | Default |
| --- | --- | --- |
| Identifiers | Government IDs, card and account numbers, phone, email, medical record numbers, credentials | Always masked |
| Contextual | Person names, addresses, employer, organisations known to the gazetteer | Masked |
| Analytical | Amounts, dates, quantities | Visible, so the assistant can do arithmetic |

Each tier can be switched in the Control Room or in configuration. Organisation names are masked only when the gazetteer knows them, because name-recognition models tag organisations too freely.

### Detectors

| Entity | Method |
| --- | --- |
| Aadhaar number | 12 digits with Verhoeff checksum |
| Card number | Digit run with Luhn checksum |
| PAN | Format `AAAAA9999A` |
| IFSC | Four letters, a zero, six alphanumerics |
| Phone, email | Pattern matching with normalisation |
| API keys and tokens | Known prefixes and high-entropy strings |
| Medical record number | Hospital-specific pattern from configuration |
| Person names | Gazetteer first. Presidio with spaCy is an optional second source. |

### Gazetteer

Generic detectors recognise patterns. They do not know who the user is. The gazetteer supplies that: the user's name and aliases, a contacts file and any extra values, all matched exactly across every payload. It is the main reason a nickname in a free-text note gets masked.

```yaml
# gazetteer.yaml (synthetic example)
self:
  names: ["Aarav Sharma", "Aarav", "A. Sharma"]
  addresses: ["12 Lake Road, Indiranagar"]
  employer: "Example Analytics Pvt Ltd"
contacts:
  source: contacts.vcf
extra:
  - value: "Meera"
    entity: PERSON
```

```yaml
# privacy_policy.yaml
tiers:
  identifiers: mask
  contextual: mask
  analytical: pass
detectors:
  custom:
    - name: hospital_record
      entity: MED_ID
      pattern: '[A-Z]{2}-\d{5}'
```

The configuration reference is in [docs/CONFIGURATION.md](docs/CONFIGURATION.md).

## Control Room

A local web interface served from the gateway process. It binds to `127.0.0.1` and takes a per-launch token.

| Pane | Contents |
| --- | --- |
| Live view | Two columns for each call: what the cloud saw, and what the laptop saw. Real values are masked until the user chooses to reveal them. |
| Approvals | Pending approval cards with the real recipient and body, flags, and approve and deny controls |
| Vault and policy | Tier switches, gazetteer sources, effect overrides, wipe and rotate |
| Catalog meter | Tools exposed against tools available, with approximate token counts |
| Audit log | A searchable record of calls, decisions and withheld payloads |

## Paperwork Pack

Ready-made local MCP servers so the system works out of the box for common paperwork. They read from folders the user chooses.

| Server | Example tools | Effect classes |
| --- | --- | --- |
| `documents` | `list_files`, `read_text` (PDF, Markdown, text), `search_files` | `read` |
| `bank` | `query_transactions`, `summarise_period` (CSV export) | `read` |
| `contacts` | `lookup_contact`, `lookup_email` | `read` |
| `notes` | `search_notes`, `read_note` | `read` |
| `mail_drafts` | `create_draft`, `list_drafts`, `send_draft` | `local_write`, `read`, `external` |

Cloakroom also wraps unmodified third-party servers. The reference filesystem server is the first test of that, since it shows the gateway needs no change to the servers it protects.

## Threat model and limitations

The full model is in [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md). The summary follows.

| Threat | Handling | Residual risk |
| --- | --- | --- |
| The cloud provider reads tool results | Cloak pipeline replaces private values with placeholders | Free-text names the gazetteer and detectors miss |
| A document or email steers the assistant into exfiltrating data | Effect-gated restoration, out-of-band approval, recipient flag | A user who approves without reading the card |
| The model invents or alters a placeholder | Placeholders are validated before any call | None beyond a failed call |
| Images and scans carry private data | Withheld | Scanned documents cannot be used |
| A server changes a tool description after installation | Planned: description pinning with re-approval | Not covered in the first version |
| A malicious downstream server | Out of scope | The server has the access its code has |
| Compromise of the local machine | Out of scope | Total |

Known limitations:

- Text the user types into the chat is not protected.
- Pseudonymisation is not anonymity. Rare details, such as an unusual diagnosis together with a city, can still point to a person. Amounts and dates are visible by default.
- Free-text names are the weakest area. The gazetteer and tripwire reduce misses without removing them.
- Stable placeholders let a provider link conversations. Rotation reduces this.
- This reduces exposure. It is not a compliance guarantee.

## Testing and evaluation

No results are reported yet. This section describes how they will be produced, and each experiment will have a script in `benchmarks/` and a committed results file.

| Experiment | Measures | Method | Acceptance criterion |
| --- | --- | --- | --- |
| Leak test | Seeded identifiers that reach the host | A synthetic corpus of bills, bank CSV, notes, emails and contacts with every identifier recorded, including hard cases (spaced digits, lowercase names, nicknames, names inside paths and error messages). The upward stream is captured and searched. Run with and without the gazetteer. | Zero leaks in the identifier tier. Contextual leaks reported per entity class. |
| Control test | Actions executed without approval | Five or more injected instructions planted in documents, run through a scripted agent that obeys them. Also tests for unknown tools, unknown placeholders and expired approvals. | No external action runs without an approval card, and the card shows the real recipient. |
| Discovery test | Needed-tool recall and tokens exposed | About twenty tasks over the real catalog, comparing full catalog, BM25 only and hybrid retrieval. A separate scaling run with synthetic filler tools, labelled as such. | Hybrid recall at least that of BM25. Exposed tokens measured, not assumed. |
| Overhead | Added latency | p50 and p95 for discovery and for the cloak pipeline | Reported as measured |

Tests run at three levels: unit tests (canonicalisation, detectors and checksums, vault, placeholder validation), integration tests with a scripted agent against the Paperwork Pack, and the experiments above. CI runs the first two. See [docs/TESTING.md](docs/TESTING.md).

## Technology

| Layer | Choice | Reason |
| --- | --- | --- |
| Language | Python 3.11 or later | The privacy and retrieval libraries are Python-first |
| MCP | Official `mcp` SDK, server and client | One SDK for both sides of the gateway |
| Dashboard | FastAPI, uvicorn, server-sent events, a single HTML page | Few dependencies and no build step |
| Storage | SQLite | Local, embedded, transactional |
| Encryption | `cryptography` (AES-256-GCM, HMAC-SHA256), `keyring` | Authenticated encryption with the key kept in the OS keychain |
| Matching | `pyahocorasick` or `ahocorasick_rs` | Fast multi-pattern matching for the gazetteer |
| Retrieval | `rank-bm25`, `sentence-transformers` | Hybrid ranking on CPU |
| Names (optional) | Presidio, spaCy | A second source for names the gazetteer lacks |
| Testing | pytest, ruff, mypy, GitHub Actions | Tests, lint and type checks on every push |

## Repository layout

```text
cloakroom/
├── README.md
├── LICENSE
├── SECURITY.md
├── pyproject.toml
├── config/
│   ├── servers.example.yaml
│   ├── privacy_policy.example.yaml
│   └── gazetteer.example.yaml
├── docs/
│   ├── ARCHITECTURE.md
│   ├── INTERFACE.md
│   ├── CONFIGURATION.md
│   ├── THREAT_MODEL.md
│   ├── DECISIONS.md
│   ├── TESTING.md
│   └── diagrams/
├── src/cloakroom/
│   ├── gateway/        # MCP front, client pool
│   ├── discovery/      # catalog, retrieval, tool cards
│   ├── cloak/          # content filter, field policy, gazetteer, detectors, tripwire
│   ├── vault/
│   ├── policy/         # effect classes, restoration rules, approvals
│   ├── controlroom/    # dashboard and event stream
│   └── cli.py
├── packs/paperwork/    # documents, bank, contacts, notes, mail_drafts
├── data/synthetic/     # all demo data
├── benchmarks/
└── tests/
```

## Related work

Redacting or pseudonymising personal data at an MCP or LLM gateway is an established pattern, and Cloakroom builds on it. The descriptions below come from public package pages and documentation. These tools have not been run as part of this project, and the table makes no claim about how complete they are.

| Project | Public description | Focus compared with Cloakroom |
| --- | --- | --- |
| mcp-shield-pii | Intercepting proxy for MCP clients and servers that redacts PII with regex and NLP, with several masking strategies including a reversible mode | Cloakroom adds a personal gazetteer, effect-gated restoration with approval, and tool discovery |
| shadow-vault | Reversible pseudonymisation at the tool boundary for agents and MCP, with a stdio gateway, an encrypted vault and a fail-closed option | Cloakroom adds out-of-band approvals tied to effect classes, the gazetteer, and tool discovery |
| mcp-audit-gateway | Gateway adding per-tool access control, audit export, tenant isolation and PII redaction on tool results | Cloakroom targets one person on one machine and has no roles or tenants |
| Gravitee, Bifrost | Enterprise AI gateways that apply PII policies to LLM and MCP traffic | Those serve administrators and organisations. Cloakroom serves an individual approving their own actions. |

## Installation and usage

The commands below describe the designed interface. They will be confirmed when the first implementation is released.

Install from a checkout of this repository:

```bash
pip install -e .
```

Import the servers already configured in Claude Desktop:

```bash
cloakroom init
```

The command backs up the existing host configuration, moves each server into Cloakroom's own `servers.yaml`, and leaves the host with a single entry.

```json
{
  "mcpServers": {
    "cloakroom": { "command": "cloakroom", "args": ["serve"] }
  }
}
```

```yaml
# config/servers.yaml (moved from the host configuration)
servers:
  filesystem:
    command: npx
    args: ["-y", "@modelcontextprotocol/server-filesystem", "~/Documents"]
    effects:
      write_file: local_write
  documents:
    command: python
    args: ["-m", "paperwork.documents", "--root", "~/Paperwork"]
relations:
  mail_drafts.create_draft: [contacts.lookup_email]
```

`init` then offers to build the gazetteer from a contacts file and a short profile. After that, restart the host and chat as usual. Approval cards appear in the Control Room, whose address is printed on the first run.

| Command | Purpose |
| --- | --- |
| `cloakroom init` | Import host configuration, create `servers.yaml` and a first gazetteer |
| `cloakroom serve` | Start the gateway. The host runs this. |
| `cloakroom vault wipe` | Delete all placeholder mappings |
| `cloakroom vault rotate` | Start a new placeholder numbering |

## Security, license and acknowledgements

### Security

Cloakroom has not been audited and should not be used with real sensitive data in its current state. Report vulnerabilities through GitHub's private vulnerability reporting for this repository. Details are in `SECURITY.md`.

### License

Released under the MIT License. See `LICENSE`.

### Synthetic data

Every name, record number, account number and document in this repository is synthetic. Any resemblance to a real person or organisation is coincidental.

### Acknowledgements

Cloakroom builds on the Model Context Protocol and its reference servers, and on the open-source libraries listed under [Technology](#technology).

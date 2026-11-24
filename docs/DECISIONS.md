# Cloakroom

## Architecture decisions

This document records the design decisions behind Cloakroom and the alternatives considered. It describes the intended architecture, not evidence that every decision has been implemented or validated.

## Gateway and trust boundary

### A single MCP gateway

Cloakroom is an MCP server to the host and an MCP client to the downstream servers. The host sees three meta-tools: `discover_tools`, `invoke_tool` and `inspect_status`.

The gateway is the common point at which tool discovery, privacy policy and approval rules are applied. Wrapping downstream servers allows existing integrations to be used without modifying their implementations.

The alternative was to expose every downstream tool directly to the host. That would retain the full tool catalog in the host-facing interface and complicate enforcement of a common placeholder and approval policy. The gateway design requires an extra discovery and invocation step, and its protection applies only to traffic routed through it.

### Protocol compatibility

The gateway relies on `tools/list` and `tools/call` for its tool interface. Newer multi round-trip request features are not a dependency because support in the target host has not been verified.

Approvals use an independent local dashboard and deferred status retrieval. Native multi round-trip support can be considered later if it proves compatible with the required approval boundary.

## Privacy and restoration

### Deterministic decisions in the trust path

The assistant does the thinking; deterministic code guards the doors. The cloak pipeline and policy engine use inspectable rules to decide what to mask and whether a call may execute.

A local language model was considered as a deeper scrubber. It was removed from the initial design because its decisions would be harder to reproduce and audit, and it would add inference overhead. A later additive-only detector may propose additional masks, but it must never remove a mask required by policy.

The embedding model used for tool discovery is separate from the privacy and approval decisions. Optional statistical name recognition is also a detection aid, not an authority for permitting disclosure.

### Personal gazetteer and tripwire

Generic detectors recognise formats and some names, but they do not know the user's aliases, contacts or addresses. Cloakroom adds a personal gazetteer and uses Aho-Corasick matching to identify known values across payloads.

The tripwire checks the final host-bound payload against real values known to the vault and gazetteer. If re-cloaking does not clear a hit, the payload is withheld. Pipeline errors also withhold data.

This decision reduces reliance on generic detection alone. It cannot establish that an unknown private value has been recognised. The leak experiment includes an ablation to measure the gazetteer's contribution.

### Filter unsupported content

Text and structured JSON are in scope. Images and binary blocks are withheld because the initial system does not have a reliable way to scrub private values from pixels or arbitrary binary formats.

This reduces the number of data paths that could bypass text masking, at the cost of excluding scanned documents from the initial workflow. Errors and tool descriptions are included in the cloak pipeline because they may contain private values too.

### Typed, stable placeholders

Placeholders use the `[TYPE_N]` form. The earlier angle-bracket format was dropped because some chat interfaces may interpret it as HTML. Rendering and round-trip behaviour still need to be checked in the target host.

The vault reuses mappings across downstream tools and conversations. Explicit aliases and canonical matching are used in place of fuzzy name merging. A wrong merge may restore the wrong person's value; separate tokens for the same person are preferable to an incorrect merge.

Stable tokens support cross-record comparison, but they also permit linkage across conversations. Wipe and rotation controls give the user control over the mapping lifecycle.

### Persistent encrypted vault

The vault uses SQLite, AES-256-GCM for encrypted values and keyed HMAC for lookups. The encryption key is held in the operating system keychain.

An in-memory-only vault was rejected because conversations can outlive the gateway process. Session-specific handles were also dropped for the initial single-user design. Keeping the vault persistent introduces key management and storage requirements that must be tested.

### Effect-gated restoration

Unrestricted restoration would let an injected instruction cause the gateway to insert real private values into an outward action. The policy engine therefore classifies the tool before permitting execution with restored values.

| Effect | Decision |
| --- | --- |
| `read` | Automatic execution |
| `local_write` | Automatic execution and audit event |
| `external` | Require user approval |
| `unknown` | Require user approval |

The classification comes from explicit configuration, server annotations and the default, in that order. Annotations are hints, not guarantees. Incorrect classification remains a security risk, and the distinction between a genuinely local write and a synchronised or remote write must be maintained.

### Out-of-band, payload-bound approval

The Control Room is the approval channel. Approval through the assistant's chat was rejected because an assistant influenced by injected text must not be able to answer on the user's behalf.

The user sees the actual payload and recipient. Approval is bound to a hash of that payload so that a different payload cannot execute under the same decision. Unanswered requests expire as denials. Deferred execution and `inspect_status` allow the host to recover the result when waiting for a human would exceed the host's call timeout.

The exact replay, concurrency and recovery rules require implementation and testing. A user can still approve an unsafe request; the gateway does not eliminate that risk.

## Tool discovery

### Hybrid retrieval

Discovery combines BM25 with embeddings from `all-MiniLM-L6-v2` using reciprocal rank fusion. BM25 captures exact vocabulary; the embedding search addresses paraphrases such as bill and invoice.

A cross-encoder reranker was considered and removed because its additional dependencies and latency were not justified for the intended catalog size. This is a design judgement, not a measured comparison. The discovery evaluation will compare BM25 and hybrid retrieval over the same tasks.

### Rewritten schemas and relations

Tool cards remove constraints such as `format: email` from parameters that may contain placeholders. The card tells the assistant that placeholders are accepted. Downstream calls still need to satisfy the original tool contract after restoration.

A small configuration map describes common tool relationships. The assistant can discover more tools when needed. This replaces the earlier schema-compatibility DAG and multi-tier inference design, which would increase implementation cost for the initial set of servers.

Signed capability cards and unverified caching fields were also removed. Tool-description pinning with re-approval remains a planned protection against changes to downstream definitions.

### Measured token exposure

Reducing tool exposure is a secondary benefit of the gateway. The project does not assume that tool search is unique to Cloakroom or that fewer definitions always improve task completion.

Evaluation uses the real catalog first. Larger catalogs containing synthetic filler tools are used only in a labelled scaling experiment. Token counts are approximate because the gateway uses a stand-in tokenizer.

## Local application and onboarding

### Control Room

The intended dashboard uses FastAPI, uvicorn, server-sent events and a single HTML/JavaScript page. It runs inside the gateway process on loopback with a random per-launch token.

A React and Cytoscape dashboard was considered when the design included a tool dependency DAG. Removing the DAG removed the reason for that visualisation stack. The Control Room instead concentrates on the live view, approval inbox, vault controls, catalog meter and audit log.

The audit log stores metadata and cloaked cloud-view payloads. The local view is reconstructed from the vault. The application must not deliberately persist raw tool payloads in diagnostic logs.

### Paperwork Pack

The Paperwork Pack provides local MCP servers for documents, bank CSV exports, contacts, notes and mail drafts. This gives the gateway a concrete everyday workflow instead of requiring users to assemble a set of integrations themselves.

The default workflow creates a local draft for the user to review and send. Real Gmail draft integration is a possible later extension and would require its own effect classification because writing to a remote service crosses the local boundary.

### Import existing configuration

The intended `cloakroom init` command imports the host's MCP configuration, backs it up and replaces the host's downstream entries with one gateway entry. It also offers to build the personal gazetteer from a local profile and contacts file.

This avoids requiring users to reconfigure every server manually. The command must preserve the existing configuration on failure; its behaviour still needs to be verified on the target operating systems and host.

## Technology choices

| Choice | Rationale |
| --- | --- |
| Python 3.11 or later | The privacy and retrieval libraries are Python-first |
| Official MCP SDK | One SDK for the gateway's server and client roles |
| FastAPI, uvicorn and SSE | Local dashboard with a small dependency footprint and event streaming |
| SQLite | Embedded transactional storage |
| `cryptography` and `keyring` | Authenticated encryption, keyed hashing and OS key management |
| `pyahocorasick` or `ahocorasick_rs` | Multi-pattern gazetteer matching |
| `rank-bm25` and `sentence-transformers` | Lexical and embedding retrieval on CPU |
| Optional Presidio and spaCy | Additional recognition of unknown names |
| pytest, Ruff, mypy and GitHub Actions | Automated testing, linting, type checking and CI |

The design no longer depends on Apple Silicon, MLX or a local generative model. The choice between the two Aho-Corasick libraries and exact dependency versions has not been finalised.

## Decisions requiring verification

| Item | What remains to be established |
| --- | --- |
| Host compatibility | Protocol revision, content types, placeholder rendering and tool-call timeout |
| Tool annotations | Availability and accuracy of annotations in the downstream servers |
| Name recognition | Recall on Indian names in the synthetic corpus |
| Catalog lifecycle | Persistence and refresh behaviour |
| Privacy configuration | Restrictions on disabling identifier masking |
| Approval execution | Replay protection, concurrent decisions and recovery behaviour |
| Vault rotation | Resolution of old placeholders and keychain failure behaviour |
| Related work | Actual behaviour of competing gateways, which have not yet been tested |

The earlier design mentioned `ttlMs` and `cacheScope`. These fields were not confirmed and are not part of the interface. No protocol compatibility or performance claim depends on them.

The evaluation methods are described in [TESTING.md](TESTING.md). Security assumptions and residual risks are recorded in [THREAT_MODEL.md](THREAT_MODEL.md).

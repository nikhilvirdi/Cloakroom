# Cloakroom

## Configuration

Cloakroom keeps the gateway configuration on the user's machine. The configuration determines which MCP servers it connects to, which values it masks and which actions require approval.

The examples below describe the intended configuration format. The final file locations, validation rules and command behaviour need to be confirmed against the implementation. All personal details in the examples are synthetic.

## Configuration files

| File | Purpose |
| --- | --- |
| `servers.yaml` | Downstream server commands, arguments, effect overrides and tool relations |
| `privacy_policy.yaml` | Privacy tiers, field policies and custom detectors |
| `gazetteer.yaml` | Personal values, aliases, contacts and additional private entities |

Example configuration files may be distributed with the project. The user's actual configuration, contacts and private documents must not be committed to the repository.

## Downstream servers

The gateway connects to each configured downstream server as an MCP client. At startup it lists the server's tools and adds them to its catalog. The server commands and arguments determine what those processes can access; they are part of the local trust boundary.

```yaml
# servers.yaml
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

| Setting | Meaning |
| --- | --- |
| `servers` | Map of downstream server identifiers and their configurations |
| `command` | Executable used to start a server |
| `args` | Arguments passed to that executable |
| `effects` | Explicit effect classifications for tools on that server |
| `relations` | Hints about tools that are commonly needed together |

The example uses the reference filesystem server and a Paperwork Pack document reader. Paths and executable names are illustrative; the final setup must resolve them correctly on the user's operating system.

### Effect overrides

Effect overrides take precedence over downstream tool annotations. They should describe the actual behaviour of the tool, including where it writes data.

| Effect | Behaviour |
| --- | --- |
| `read` | Executes automatically when the call is valid |
| `local_write` | Executes automatically and is logged |
| `external` | Requires approval before execution |
| `unknown` | Treated as `external` |

A write to a cloud-synchronised folder is not necessarily local in effect. A tool must not be classified as `local_write` simply because it writes through a local process. Server annotations are hints, not guarantees.

The [threat model](THREAT_MODEL.md) describes the consequences of an incorrect classification.

### Relations

The relations map provides discovery hints. For example, creating a mail draft often requires looking up the recipient's email address first. A relation does not invoke a tool, grant permission or override its effect classification.

See [the MCP interface](INTERFACE.md) for tool cards and invocation contracts.

## Privacy policy

### Tiers

| Tier | Examples | Default |
| --- | --- | --- |
| Identifiers | Government IDs, card and account numbers, phone, email, medical record numbers, credentials | Mask |
| Contextual | Person names, addresses, employer, organisations known to the gazetteer | Mask |
| Analytical | Amounts, dates, quantities | Pass |

Amounts and dates remain visible by default so the assistant can compare transactions and perform arithmetic. This also means that a cloaked payload can retain identifying context. Pseudonymisation reduces exposure; it does not make the payload anonymous.

The tiers can be controlled through configuration or the Control Room. The design describes identifiers as always masked under the default policy. The exact restrictions on disabling identifier masking still need to be specified.

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

### Field policy

The field policy masks named fields from configured downstream servers. A field such as `account_no`, `patient_name` or `email` can be treated as private without relying on a detector to recognise the value.

This is useful for structured JSON results. It does not establish that every private field in an arbitrary response has been configured. The exact syntax for server-specific field mappings is not yet defined.

### Detectors

| Entity | Detection method |
| --- | --- |
| Aadhaar number | Twelve digits with Verhoeff checksum |
| Card number | Digit run with Luhn checksum |
| PAN | Format `AAAAA9999A` |
| IFSC | Four letters, a zero, six alphanumerics |
| Phone and email | Pattern matching with normalisation |
| API keys and tokens | Known prefixes and high-entropy strings |
| Medical record number | Configurable hospital-specific pattern |
| Person names | Gazetteer first; Presidio with spaCy is an optional second source |

Checksums reduce false positives for identifiers that have a checksum scheme. They do not establish that a value belongs to a particular person. Custom patterns are needed for identifiers whose formats differ between organisations.

Custom detector rules specify a name, an entity type and a pattern. In the example above, the hospital record rule identifies values such as `LH-99214` as `MED_ID`. The final implementation needs to validate patterns before accepting the configuration.

## Personal gazetteer

Generic detectors recognise patterns. They do not know who the user is. The gazetteer supplies the user's names, aliases, contacts, addresses and any additional values they want masked.

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

| Setting | Purpose |
| --- | --- |
| `self.names` | Known names and aliases of the user |
| `self.addresses` | Addresses to recognise in returned data |
| `self.employer` | Known organisation name |
| `contacts.source` | Local contacts file used to build the gazetteer |
| `extra` | Additional values and their entity types |

The gateway uses Aho-Corasick matching to find known values in strings returned by downstream servers. Alias mappings allow the vault to associate explicitly known variants with the same entity. Names are not merged by fuzzy similarity.

The gazetteer is sensitive data in its own right. It contains the very values that Cloakroom is intended to keep from the cloud. It must stay local and must not appear in logs or example configuration committed to Git.

## Vault and key management

The vault stores placeholder mappings in SQLite. Real values are encrypted with AES-256-GCM, and canonical values are looked up using a keyed HMAC. The encryption key belongs in the operating system keychain.

The user can wipe the vault or rotate its placeholders through the Control Room. The intended CLI also exposes these operations:

```bash
cloakroom vault wipe
cloakroom vault rotate
```

These operations affect the ability to resolve placeholders from older conversations. Rotation reduces the linkability of future conversations but does not remove tokens already held by a cloud provider.

The final behaviour of rotation, keychain failures and recovery of encrypted mappings needs to be specified before these commands are released.

## Host setup

The intended `cloakroom init` command imports the user's existing MCP configuration, backs it up and replaces the host's downstream entries with a single Cloakroom entry.

```json
{
  "mcpServers": {
    "cloakroom": {
      "command": "cloakroom",
      "args": ["serve"]
    }
  }
}
```

The command also offers to build the gazetteer from a local contacts file and a short profile. The imported downstream configuration remains local to the gateway. The backup may contain credentials and must be treated as private configuration.

## Control Room

The Control Room runs on the loopback interface (`127.0.0.1`) and requires a random per-launch token. Its approval channel is separate from the host's MCP connection.

The intended controls include privacy tiers, gazetteer sources, effect overrides and vault operations. The binding port, token delivery mechanism and settings persistence format have not yet been finalised.

## Environment variables and secrets

No public environment variable names or precedence rules have been finalised. The implementation should document them once they exist rather than introduce names that the gateway does not recognise.

The configuration and secret-handling requirements are:

- Keep credentials out of committed configuration examples and source code.
- Use the operating system keychain for vault keys.
- Keep the Control Room token out of logs and cloud-visible payloads.
- Pass downstream credentials only where the configured server requires them.
- Keep private configuration, vault files and local data exports out of version control.
- Reject invalid configuration without silently weakening privacy or approval rules.

The exact configuration search paths, environment overrides, schema validation and reload behaviour remain implementation decisions.

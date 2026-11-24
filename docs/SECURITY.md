# Cloakroom

## Security policy

Cloakroom is a local MCP gateway designed to reduce the disclosure of personal values through tool traffic and control actions requested by an AI assistant.

The project is under development and has not been independently audited. Do not use it with real sensitive data in its current state. Development, testing and demonstrations use synthetic data.

## Reporting a vulnerability

Report security vulnerabilities through [GitHub's private vulnerability reporting](https://github.com/nikhilvirdi/Cloakroom/security/advisories/new).

Do not open a public issue containing an unpatched vulnerability, private data, credentials, vault contents or unredacted logs. If possible, reproduce the issue with synthetic data.

A useful report includes:

- The affected commit or version and operating environment.
- The relevant gateway and downstream server configuration, with secrets removed.
- Steps to reproduce the issue and the expected and observed behaviour.
- The affected trust boundary and the potential security impact.
- Sanitised logs or a minimal synthetic reproduction, where available.

No fixed response or remediation timeline has been established.

## Security scope

Reports of particular interest include:

| Area | Examples |
| --- | --- |
| Privacy boundary | Private values reaching the host through results, errors or tool descriptions |
| Approval enforcement | An external action executing without the required user approval |
| Restoration | Incorrect placeholder resolution or restoration into an unauthorised action |
| Approval integrity | Payload changes after approval, replay or unauthorised decisions |
| Local storage | Exposure of vault values, encryption keys, credentials or private configuration |
| Control Room | Unauthorised access to local views, settings or approval endpoints |
| Logging | Sensitive values persisted in diagnostic or audit records |
| Failure handling | Raw data returned after a cloak failure or unsafe retry of a downstream write |

## Security limitations

Cloakroom protects tool traffic routed through the gateway. It does not protect text entered directly into the host's chat, or traffic that bypasses the gateway.

Pseudonymisation is not anonymity. Unknown private values may escape detection, and analytical information such as dates and amounts remains visible under the default policy. Stable placeholders can permit linkage across conversations.

The gateway trusts installed downstream servers to behave as their code and configuration describe. It does not sandbox or audit their internal behaviour. A compromised local machine is outside the threat model.

See [the threat model](docs/THREAT_MODEL.md) for trust boundaries, designed mitigations and residual risks. The [evaluation document](docs/TESTING.md) describes how privacy and approval enforcement will be tested.

## Handling sensitive data

Keep real personal records, private configuration, vault files and credentials out of the repository. Do not include them in issue reports, screenshots, logs or test fixtures.

The project does not claim regulatory compliance or complete protection against disclosure.

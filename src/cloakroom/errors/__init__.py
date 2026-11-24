"""Application exceptions with messages designed for operator diagnostics."""

from enum import StrEnum


class CloakroomError(Exception):
    """Base class for an application failure with a public, static diagnostic."""

    message = "Cloakroom operation failed."

    def __init__(self) -> None:
        super().__init__(self.message)


class ConfigFile(StrEnum):
    """Fixed filenames used in configuration diagnostics."""

    SERVERS = "servers.yaml"
    PRIVACY_POLICY = "privacy_policy.yaml"
    GAZETTEER = "gazetteer.yaml"


class ConfigProblem(StrEnum):
    """Public descriptions of configuration failure categories."""

    SETTINGS = "Set CLOAKROOM_CONFIG_DIR to a path and CLOAKROOM_LOG_LEVEL to a valid level."
    DIRECTORY = "The configuration directory could not be resolved."
    MISSING = "Required configuration file is missing."
    UNREADABLE = "Configuration file could not be read as UTF-8."
    YAML = "Use valid YAML with unique keys and standard tags."
    SCHEMA = "Configuration fields or values are invalid. Compare with the matching example."


class ConfigurationError(CloakroomError):
    """Configuration could not be read or validated."""

    def __init__(self, problem: ConfigProblem, file: ConfigFile | None = None) -> None:
        self.problem = problem
        self.file = file
        self.message = f"{file}: {problem}" if file is not None else str(problem)
        super().__init__()


class GatewayError(CloakroomError):
    """The gateway cannot complete its operation."""

    message = "Gateway operation failed."


class PrivacyPipelineError(CloakroomError):
    """A payload could not pass the privacy pipeline."""

    message = "Privacy pipeline failed."


class VaultError(CloakroomError):
    """A local vault operation failed."""

    message = "Vault operation failed."


class PolicyError(CloakroomError):
    """A policy rule could not be evaluated or applied."""

    message = "Policy operation failed."

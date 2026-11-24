"""Application errors expose stable operator diagnostics."""

from typing import TypeAlias

import pytest

from cloakroom.errors import (
    CloakroomError,
    ConfigFile,
    ConfigProblem,
    ConfigurationError,
    GatewayError,
    PolicyError,
    PrivacyPipelineError,
    VaultError,
)

ErrorClass: TypeAlias = type[CloakroomError]


@pytest.mark.parametrize("kind", [GatewayError, PrivacyPipelineError, VaultError, PolicyError])
def test_subsystems_use_public_diagnostics(kind: ErrorClass) -> None:
    with pytest.raises(CloakroomError) as failure:
        raise kind()
    assert str(failure.value) == kind.message


def test_configuration_error_carries_safe_context() -> None:
    failure = ConfigurationError(ConfigProblem.MISSING, ConfigFile.SERVERS)
    assert isinstance(failure, CloakroomError)
    assert failure.file is ConfigFile.SERVERS
    assert failure.problem is ConfigProblem.MISSING
    assert str(failure) == "servers.yaml: Required configuration file is missing."

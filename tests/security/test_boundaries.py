"""Verify that synthetic private values cannot escape foundation diagnostics."""

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest

from cloakroom.configuration import load_configuration
from cloakroom.errors import ConfigProblem, ConfigurationError
from cloakroom.observability import LogLevel, configure_logging


def test_formatter_ignores_arguments_exceptions_and_unknown_metadata(
    application_logger: logging.Logger, capsys: pytest.CaptureFixture[str]
) -> None:
    configure_logging(LogLevel.DEBUG)
    logger = application_logger.getChild("fictional-private-identifier")
    try:
        raise ValueError("synthetic-secret-in-exception")
    except ValueError:
        logger.exception(
            "private arguments: %s",
            "synthetic-secret-in-arguments",
            extra={
                "app_event": "fictional-private-identifier",
                "event_id": "synthetic-token",
                "config_file": "synthetic-secret-path",
                "payload": "synthetic-payload",
            },
        )
    capture = capsys.readouterr()
    assert not capture.out
    assert not any(
        secret in capture.err for secret in ("synthetic", "fictional-private-identifier")
    )
    assert set(json.loads(capture.err)) == {"timestamp", "severity", "logger", "event"}
    assert json.loads(capture.err)["event"] == "diagnostic"


@pytest.mark.parametrize(
    ("contents", "problem"),
    [
        ("private-key-marker: [synthetic-value-marker", ConfigProblem.YAML),
        ("private-key-marker: synthetic-value-marker", ConfigProblem.SCHEMA),
        ("!!python/object:synthetic-value-marker {}", ConfigProblem.YAML),
        ("!!omap [private-key-marker: synthetic-value-marker]", ConfigProblem.SCHEMA),
    ],
)
def test_safe_yaml_errors_do_not_disclose_inputs(
    tmp_path: Path, contents: str, problem: ConfigProblem
) -> None:
    directory = tmp_path / "private-directory-marker"
    directory.mkdir()
    (directory / "servers.yaml").write_text(contents, encoding="utf-8")
    with pytest.raises(ConfigurationError) as failure:
        load_configuration(config_dir=directory)
    assert failure.value.problem is problem
    output = str(failure.value) + repr(failure.value)
    assert "marker" not in output
    assert failure.value.__suppress_context__


def test_package_imports_without_runtime_side_effects(tmp_path: Path) -> None:
    script = """\
import logging
import sys

checking_imports = True

def guard(event, _args):
    if checking_imports and event.startswith(('socket.', 'sqlite3.', 'subprocess.', 'os.mkdir')):
        raise AssertionError(event)

sys.addaudithook(guard)
import cloakroom
import cloakroom.__main__
import cloakroom.cloak
import cloakroom.configuration
import cloakroom.controlroom
import cloakroom.discovery
import cloakroom.gateway
import cloakroom.observability
import cloakroom.policy
import cloakroom.vault
assert not logging.getLogger('cloakroom').handlers
# Coverage may use SQLite to write its report during interpreter shutdown.
checking_imports = False
"""
    result = subprocess.run(
        [sys.executable, "-B", "-c", script],
        env={**os.environ, "CLOAKROOM_CONFIG_DIR": "missing"},
        cwd=tmp_path,
        capture_output=True,
        check=False,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr.decode()
    assert not result.stdout
    assert not result.stderr
    assert not list(tmp_path.iterdir())

"""Exercise both installed command entry points in separate processes."""

import os
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

import pytest


def run_cli(
    directory: Path, *arguments: str, module: bool = True
) -> subprocess.CompletedProcess[str]:
    executable = Path(sys.executable).with_name("cloakroom.exe" if os.name == "nt" else "cloakroom")
    command = [sys.executable, "-m", "cloakroom"] if module else [str(executable)]
    return subprocess.run(
        [*command, *arguments],
        cwd=directory,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=15,
    )


@pytest.mark.parametrize("module", [True, False])
def test_help_and_version(tmp_path: Path, module: bool) -> None:
    help_result = run_cli(tmp_path, "--help", module=module)
    assert help_result.returncode == 0
    assert "check-config" in help_result.stdout
    assert not help_result.stderr

    version_result = run_cli(tmp_path, "--version", module=module)
    assert version_result.returncode == 0
    assert version_result.stdout.strip() == "cloakroom " + version("cloakroom")
    assert not version_result.stderr


def test_bare_module_displays_usage(tmp_path: Path) -> None:
    result = run_cli(tmp_path)
    assert result.returncode == 0
    assert "usage: cloakroom" in result.stdout
    assert not result.stderr


@pytest.mark.parametrize(
    "arguments", [("serve",), ("--private-input=fictional",), ("check-config", "--config-dir", "")]
)
def test_invalid_arguments_are_sanitised(tmp_path: Path, arguments: tuple[str, ...]) -> None:
    result = run_cli(tmp_path, *arguments)
    assert result.returncode == 2
    assert not result.stdout
    assert "invalid arguments" in result.stderr
    assert "fictional" not in result.stderr


def test_check_config_keeps_stdout_clear(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLOAKROOM_LOG_LEVEL", "INFO")
    result = run_cli(tmp_path, "check-config")
    assert result.returncode == 0
    assert not result.stdout
    assert '"event": "configuration.validated"' in result.stderr


def test_check_config_reports_missing_files_on_stderr(tmp_path: Path) -> None:
    result = run_cli(tmp_path, "check-config", "--config-dir", "sensitive-path-fixture")
    assert result.returncode == 1
    assert not result.stdout
    assert '"event": "configuration.failed"' in result.stderr
    assert "servers.yaml: Required configuration file is missing." in result.stderr
    assert "sensitive-path-fixture" not in result.stderr

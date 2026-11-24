"""Verify explicit settings and validated YAML with synthetic values."""

from pathlib import Path
from shutil import copyfile

import pytest

from cloakroom.configuration import load_configuration
from cloakroom.errors import ConfigFile, ConfigProblem, ConfigurationError
from cloakroom.observability import LogLevel

_EXAMPLES = Path(__file__).resolve().parents[2] / "config"


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    for file in ConfigFile:
        path = Path(file)
        copyfile(_EXAMPLES / f"{path.stem}.example.yaml", tmp_path / file)
    return tmp_path


def test_documented_examples_load(config_dir: Path) -> None:
    config = load_configuration(config_dir=config_dir)
    assert config.servers.servers["filesystem"].command == "npx"
    assert config.servers.relations["mail_drafts.create_draft"] == ["contacts.lookup_email"]
    assert config.privacy_policy.detectors.custom[0].entity == "MED_ID"
    assert config.gazetteer.personal_values.names == ["Demo Person", "D. Person"]
    assert config.gazetteer.contacts is not None
    assert config.gazetteer.contacts.source == "contacts.vcf"


def test_secure_defaults_do_not_scan_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("CLOAKROOM_LOG_LEVEL=DEBUG", encoding="utf-8")
    (tmp_path / "servers.yaml").write_text("broken: [", encoding="utf-8")
    config = load_configuration()
    assert config.settings.config_dir is None
    assert config.settings.log_level is LogLevel.WARNING
    assert config.servers.servers == {}
    assert config.gazetteer.extra == []
    assert config.privacy_policy.tiers.model_dump() == {
        "identifiers": "mask",
        "contextual": "mask",
        "analytical": "pass",
    }


def test_environment_and_explicit_precedence(
    config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(config_dir.parent)
    monkeypatch.setenv("CLOAKROOM_CONFIG_DIR", config_dir.name)
    monkeypatch.setenv("CLOAKROOM_LOG_LEVEL", "DEBUG")
    assert load_configuration().settings.log_level is LogLevel.DEBUG
    monkeypatch.setenv("CLOAKROOM_CONFIG_DIR", "missing-directory")
    config = load_configuration(config_dir=config_dir, log_level=LogLevel.INFO)
    assert config.settings.config_dir == config_dir
    assert config.settings.log_level is LogLevel.INFO


@pytest.mark.parametrize(
    ("file", "text", "problem"),
    [
        (ConfigFile.SERVERS, "servers: [", ConfigProblem.YAML),
        (ConfigFile.SERVERS, "servers: {}\nservers: {}\n", ConfigProblem.YAML),
        (ConfigFile.SERVERS, "servers: {example: {command: false}}", ConfigProblem.SCHEMA),
        (
            ConfigFile.SERVERS,
            "servers: {example: {command: demo, effects: {read: delete}}}",
            ConfigProblem.SCHEMA,
        ),
        (ConfigFile.PRIVACY_POLICY, "tiers: {identifiers: allow}", ConfigProblem.SCHEMA),
        (
            ConfigFile.PRIVACY_POLICY,
            "detectors: {custom: [{name: sample, entity: MED_ID, pattern: '['}]}",
            ConfigProblem.SCHEMA,
        ),
        (ConfigFile.GAZETTEER, "extra: [{value: demo, entity: ALIEN}]", ConfigProblem.SCHEMA),
        (ConfigFile.GAZETTEER, "null", ConfigProblem.SCHEMA),
    ],
)
def test_reject_invalid_configuration(
    config_dir: Path, file: ConfigFile, text: str, problem: ConfigProblem
) -> None:
    (config_dir / file).write_text(text, encoding="utf-8")
    with pytest.raises(ConfigurationError) as failure:
        load_configuration(config_dir=config_dir)
    assert failure.value.file is file
    assert failure.value.problem is problem


def test_missing_file_does_not_fall_back(config_dir: Path) -> None:
    (config_dir / ConfigFile.GAZETTEER).unlink()
    with pytest.raises(ConfigurationError, match=r"gazetteer\.yaml: Required configuration file"):
        load_configuration(config_dir=config_dir)


def test_invalid_utf8_is_safe(config_dir: Path) -> None:
    (config_dir / ConfigFile.GAZETTEER).write_bytes(b"\xff")
    with pytest.raises(ConfigurationError) as failure:
        load_configuration(config_dir=config_dir)
    assert failure.value.problem is ConfigProblem.UNREADABLE


@pytest.mark.parametrize(
    ("name", "value"),
    [("CLOAKROOM_LOG_LEVEL", "invalid"), ("CLOAKROOM_CONFIG_DIR", "")],
)
def test_invalid_environment_is_rejected(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(ConfigurationError) as failure:
        load_configuration()
    assert failure.value.problem is ConfigProblem.SETTINGS

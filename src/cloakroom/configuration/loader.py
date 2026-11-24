"""Load explicitly selected configuration files with safe diagnostics."""

from pathlib import Path
from typing import TypedDict, TypeVar

import yaml
from pydantic import BaseModel, ValidationError
from pydantic_settings import SettingsError
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode

from cloakroom.configuration.models import (
    Configuration,
    Gazetteer,
    PrivacyPolicy,
    Servers,
    Settings,
)
from cloakroom.errors import ConfigFile, ConfigProblem, ConfigurationError
from cloakroom.observability import LogLevel

_Model = TypeVar("_Model", bound=BaseModel)


class _Overrides(TypedDict, total=False):
    config_dir: Path
    log_level: LogLevel


class _UniqueKeyLoader(yaml.SafeLoader):
    def construct_mapping(self, node: MappingNode, deep: bool = False) -> dict[object, object]:
        self.flatten_mapping(node)
        mapping = super().construct_mapping(node, deep=deep)
        if len(mapping) != len(node.value):
            raise ConstructorError(None, None, "duplicate mapping key", node.start_mark)
        return mapping


def _load_file(directory: Path, file: ConfigFile, model: type[_Model]) -> _Model:
    try:
        contents = (directory / file).read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ConfigurationError(ConfigProblem.MISSING, file) from None
    except (OSError, UnicodeError, ValueError):
        raise ConfigurationError(ConfigProblem.UNREADABLE, file) from None

    try:
        raw: object = yaml.load(contents, Loader=_UniqueKeyLoader)
    except (yaml.YAMLError, TypeError, ValueError, RecursionError, OverflowError):
        raise ConfigurationError(ConfigProblem.YAML, file) from None

    try:
        return model.model_validate(raw)
    except ValidationError:
        raise ConfigurationError(ConfigProblem.SCHEMA, file) from None


def load_configuration(
    *,
    config_dir: Path | None = None,
    log_level: LogLevel | None = None,
) -> Configuration:
    """Load explicit overrides, then environment settings, then secure defaults.

    A specified directory must contain all three named files. With no directory,
    no YAML, dotenv file or home-directory configuration is read.
    """
    overrides: _Overrides = {}
    if config_dir is not None:
        overrides["config_dir"] = config_dir
    if log_level is not None:
        overrides["log_level"] = log_level
    try:
        settings = Settings(**overrides)
    except (SettingsError, ValidationError):
        raise ConfigurationError(ConfigProblem.SETTINGS) from None

    if settings.config_dir is None:
        return Configuration(settings=settings)

    try:
        directory = settings.config_dir.expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        raise ConfigurationError(ConfigProblem.DIRECTORY) from None

    return Configuration(
        settings=settings,
        servers=_load_file(directory, ConfigFile.SERVERS, Servers),
        privacy_policy=_load_file(directory, ConfigFile.PRIVACY_POLICY, PrivacyPolicy),
        gazetteer=_load_file(directory, ConfigFile.GAZETTEER, Gazetteer),
    )

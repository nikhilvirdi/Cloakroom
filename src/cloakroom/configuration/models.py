"""Validated schemas for settings and the documented YAML files."""

import re
from pathlib import Path
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

from cloakroom.observability import LogLevel


def _require_non_blank(value: object) -> object:
    if isinstance(value, str) and not value.strip():
        raise ValueError("must not be blank")
    return value


NonBlank = Annotated[str, StringConstraints(strict=True), BeforeValidator(_require_non_blank)]
Effect = Literal["read", "local_write", "external", "unknown"]
Setting = Literal["mask", "pass"]
Entity = Literal["PERSON", "ORG", "EMAIL", "PHONE", "ACCT", "GOVID", "MED_ID", "ADDR", "SECRET"]


class _YamlModel(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class Settings(BaseSettings):
    """Process settings. Explicit values override the environment and defaults."""

    model_config = SettingsConfigDict(
        env_prefix="CLOAKROOM_", env_file=None, hide_input_in_errors=True
    )
    config_dir: Annotated[Path, BeforeValidator(_require_non_blank)] | None = Field(
        default=None, repr=False
    )
    log_level: LogLevel = LogLevel.WARNING


class Server(_YamlModel):
    command: NonBlank = Field(repr=False)
    args: list[str] = Field(default_factory=list, repr=False)
    effects: dict[NonBlank, Effect] = Field(default_factory=dict, repr=False)


class Servers(_YamlModel):
    servers: dict[NonBlank, Server] = Field(default_factory=dict, repr=False)
    relations: dict[NonBlank, list[NonBlank]] = Field(default_factory=dict, repr=False)


class Tiers(_YamlModel):
    identifiers: Setting = "mask"
    contextual: Setting = "mask"
    analytical: Setting = "pass"


class Detector(_YamlModel):
    name: NonBlank = Field(repr=False)
    entity: Entity
    pattern: NonBlank = Field(repr=False)

    @field_validator("pattern")
    @classmethod
    def _validate_pattern(cls, value: str) -> str:
        try:
            re.compile(value)
        except (re.error, OverflowError, RecursionError):
            raise ValueError("invalid regular expression") from None
        return value


class Detectors(_YamlModel):
    custom: list[Detector] = Field(default_factory=list, repr=False)


class PrivacyPolicy(_YamlModel):
    tiers: Tiers = Field(default_factory=Tiers)
    detectors: Detectors = Field(default_factory=Detectors, repr=False)


class PersonalValues(_YamlModel):
    names: list[NonBlank] = Field(default_factory=list, repr=False)
    addresses: list[NonBlank] = Field(default_factory=list, repr=False)
    employer: NonBlank | None = Field(default=None, repr=False)


class Contacts(_YamlModel):
    source: NonBlank = Field(repr=False)


class PrivateValue(_YamlModel):
    value: NonBlank = Field(repr=False)
    entity: Entity


class Gazetteer(_YamlModel):
    personal_values: PersonalValues = Field(
        default_factory=PersonalValues, alias="self", repr=False
    )
    contacts: Contacts | None = Field(default=None, repr=False)
    extra: list[PrivateValue] = Field(default_factory=list, repr=False)


class Configuration(BaseModel):
    """The complete validated configuration for one process."""

    settings: Settings
    servers: Servers = Field(default_factory=Servers, repr=False)
    privacy_policy: PrivacyPolicy = Field(default_factory=PrivacyPolicy)
    gazetteer: Gazetteer = Field(default_factory=Gazetteer, repr=False)

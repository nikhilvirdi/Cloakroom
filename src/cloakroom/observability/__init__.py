"""Structured diagnostics for the Cloakroom application logger.

Event names and metadata come from explicit allowlists. Application logs do not
render arbitrary log messages, arguments, stack traces or exception text.
"""

import json
import logging
import sys
from datetime import UTC, datetime
from enum import StrEnum
from threading import Lock
from uuid import UUID

from cloakroom.errors import ConfigFile, ConfigProblem, ConfigurationError


class LogLevel(StrEnum):
    """Levels accepted by the application logging configuration."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class Event(StrEnum):
    """Supported diagnostic events."""

    CONFIGURATION_VALIDATED = "configuration.validated"
    CONFIGURATION_FAILED = "configuration.failed"
    APPLICATION_FAILED = "application.failed"


_LOGGER = "cloakroom"
_LOGGER_NAMES = frozenset({_LOGGER, "cloakroom.cli", "cloakroom.configuration"})
_SEVERITIES = {
    logging.DEBUG: LogLevel.DEBUG,
    logging.INFO: LogLevel.INFO,
    logging.WARNING: LogLevel.WARNING,
    logging.ERROR: LogLevel.ERROR,
    logging.CRITICAL: LogLevel.CRITICAL,
}
_CONFIGURE_LOCK = Lock()


class _SafeFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        event = getattr(record, "app_event", None)
        event_id = getattr(record, "event_id", None)
        config_file = getattr(record, "config_file", None)
        config_problem = getattr(record, "config_problem", None)
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "severity": _SEVERITIES.get(record.levelno, LogLevel.WARNING),
            "logger": record.name if record.name in _LOGGER_NAMES else _LOGGER,
            "event": event if isinstance(event, Event) else "diagnostic",
        }
        if isinstance(event_id, UUID):
            payload["event_id"] = str(event_id)
        if event is Event.CONFIGURATION_FAILED:
            if isinstance(config_file, ConfigFile):
                payload["file"] = config_file
            if isinstance(config_problem, ConfigProblem):
                payload["reason"] = config_problem.name.lower()
        return json.dumps(payload, ensure_ascii=True)


class _StderrHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.setFormatter(_SafeFormatter())

    def emit(self, record: logging.LogRecord) -> None:
        # The standard handler's error fallback can print raw messages and arguments.
        sys.stderr.write(self.format(record) + "\n")
        sys.stderr.flush()


def configure_logging(level: LogLevel = LogLevel.WARNING) -> logging.Logger:
    """Configure only Cloakroom's logger with one stderr handler."""
    logger = logging.getLogger(_LOGGER)
    with _CONFIGURE_LOCK:
        if len(logger.handlers) != 1 or not isinstance(logger.handlers[0], _StderrHandler):
            logger.handlers = [_StderrHandler()]
        logger.propagate = False
        logger.setLevel(level.value)
    return logger


def log_event(
    logger: logging.Logger,
    level: LogLevel,
    event: Event,
    *,
    event_id: UUID | None = None,
    configuration_error: ConfigurationError | None = None,
) -> None:
    """Emit an event with typed, allowlisted metadata."""
    logger.log(
        logging.getLevelNamesMapping()[level],
        event.value,
        extra={
            "app_event": event,
            "event_id": event_id,
            "config_file": configuration_error.file if configuration_error else None,
            "config_problem": configuration_error.problem if configuration_error else None,
        },
    )

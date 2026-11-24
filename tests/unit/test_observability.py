"""Test structured stderr logging and idempotent configuration."""

import json
import logging
from datetime import datetime
from uuid import UUID

import pytest

from cloakroom.observability import Event, LogLevel, configure_logging, log_event


def test_reconfigure_levels_without_duplicate_handlers(
    application_logger: logging.Logger, capsys: pytest.CaptureFixture[str]
) -> None:
    logger = configure_logging(LogLevel.ERROR)
    assert logger is application_logger
    handler = logger.handlers[0]
    log_event(logger, LogLevel.INFO, Event.CONFIGURATION_VALIDATED)
    assert configure_logging(LogLevel.INFO) is logger
    event_id = UUID(int=42)
    log_event(logger, LogLevel.INFO, Event.CONFIGURATION_VALIDATED, event_id=event_id)

    captured = capsys.readouterr()
    assert not captured.out
    assert logger.handlers == [handler]
    assert not logger.propagate
    assert len(captured.err.splitlines()) == 1
    entry = json.loads(captured.err)
    assert datetime.fromisoformat(entry.pop("timestamp")).utcoffset().total_seconds() == 0
    assert entry == {
        "severity": "INFO",
        "logger": "cloakroom",
        "event": "configuration.validated",
        "event_id": str(event_id),
    }

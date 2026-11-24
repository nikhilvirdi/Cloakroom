"""Isolate application configuration from the developer's environment."""

import logging
import os
from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(os.environ):
        if name.upper().startswith("CLOAKROOM_"):
            monkeypatch.delenv(name)


@pytest.fixture
def application_logger() -> Iterator[logging.Logger]:
    logger = logging.getLogger("cloakroom")
    handlers, level, propagate = logger.handlers[:], logger.level, logger.propagate
    try:
        yield logger
    finally:
        for handler in logger.handlers:
            if handler not in handlers:
                handler.close()
        logger.handlers[:] = handlers
        logger.setLevel(level)
        logger.propagate = propagate

"""Cloakroom's configuration and package command-line entry point."""

import argparse
import sys
from collections.abc import Sequence
from importlib.metadata import version
from pathlib import Path
from typing import NoReturn

from cloakroom.configuration import load_configuration
from cloakroom.errors import CloakroomError, ConfigurationError
from cloakroom.observability import Event, LogLevel, configure_logging, log_event


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        # Arguments can contain private filesystem paths.
        self.print_usage(sys.stderr)
        self.exit(2, "cloakroom: invalid arguments. Run cloakroom --help for usage.\n")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return an appropriate process exit status."""
    parser = _Parser(prog="cloakroom", description="Cloakroom local privacy gateway")
    parser.add_argument("--version", action="version", version=f"%(prog)s {version('cloakroom')}")
    commands = parser.add_subparsers(dest="command")
    check = commands.add_parser("check-config", help="validate local configuration")
    check.add_argument(
        "--config-dir", metavar="PATH", help="directory containing the three YAML files"
    )
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    logger = configure_logging()
    try:
        if args.config_dir is not None and not args.config_dir.strip():
            check.error("empty configuration directory")
        directory = Path(args.config_dir) if args.config_dir is not None else None
        configuration = load_configuration(config_dir=directory)
    except ConfigurationError as error:
        log_event(logger, LogLevel.ERROR, Event.CONFIGURATION_FAILED, configuration_error=error)
        print(f"cloakroom: {error}", file=sys.stderr)
        return 1
    except CloakroomError:
        log_event(logger, LogLevel.ERROR, Event.APPLICATION_FAILED)
        return 1

    configure_logging(configuration.settings.log_level)
    log_event(logger, LogLevel.INFO, Event.CONFIGURATION_VALIDATED)
    return 0

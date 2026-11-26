"""Cloakroom's configuration and package command-line entry point."""

import argparse
import asyncio
import secrets
import sys
from collections.abc import Sequence
from importlib.metadata import version
from pathlib import Path
from typing import Any, NoReturn

from cloakroom.configuration import load_configuration
from cloakroom.contracts import EffectClass
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

    # check-config command
    check = commands.add_parser("check-config", help="validate local configuration")
    check.add_argument(
        "--config-dir", metavar="PATH", help="directory containing the three YAML files"
    )

    # serve command
    serve = commands.add_parser("serve", help="start the Cloakroom MCP gateway")
    serve.add_argument(
        "--config-dir", metavar="PATH", help="directory containing the three YAML files"
    )
    serve.add_argument(
        "--control-room-port",
        type=int,
        default=0,
        metavar="PORT",
        help="Control Room HTTP port (0 = auto-assign, default: 0)",
    )

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    logger = configure_logging()

    # Handle check-config command
    if args.command == "check-config":
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

    # Handle serve command
    if args.command == "serve":
        try:
            if args.config_dir is not None and not args.config_dir.strip():
                serve.error("empty configuration directory")
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

        # Run the serve command
        try:
            return asyncio.run(_serve(configuration, args.control_room_port))
        except KeyboardInterrupt:
            print("\ncloakroom: shutting down", file=sys.stderr)
            return 0
        except Exception as error:
            log_event(logger, LogLevel.ERROR, Event.APPLICATION_FAILED)
            print(f"cloakroom: {error}", file=sys.stderr)
            return 1

    return 0


async def _serve(configuration: Any, control_room_port: int) -> int:
    """Run the Cloakroom gateway server.

    Args:
        configuration: Loaded configuration
        control_room_port: Control Room HTTP port (0 = auto-assign)

    Returns:
        Exit code
    """
    from cloakroom.discovery.engine import DiscoveryEngine
    from cloakroom.gateway.pool import ClientPool, ServerConfig
    from cloakroom.gateway.server import GatewayServer, run_gateway_server
    from cloakroom.gateway.test_doubles import DummyCloakEngine, DummyEventBus
    from cloakroom.policy.approval import ApprovalManager

    logger = configure_logging()

    # Generate Control Room token
    token = secrets.token_urlsafe(24)

    # Initialize components
    log_event(logger, LogLevel.INFO, Event.CONFIGURATION_VALIDATED)

    # Create test doubles (until Dev A's implementation is merged)
    cloak_engine = DummyCloakEngine()
    event_bus = DummyEventBus()

    # Create approval manager with known contacts from config
    known_contacts = set()
    if hasattr(configuration, "contacts") and configuration.contacts:
        for contact in configuration.contacts:
            if hasattr(contact, "email") and contact.email:
                known_contacts.add(contact.email)

    approval_manager = ApprovalManager(
        wait_timeout=30.0,  # 30s wait for decision
        approval_expiry=120.0,  # 120s approval expiry (live demo default)
        known_contacts=known_contacts,
    )

    # Create client pool for downstream servers
    server_configs = []
    if hasattr(configuration, "servers") and configuration.servers:
        for server in configuration.servers:
            if hasattr(server, "id") and hasattr(server, "command"):
                server_configs.append(
                    ServerConfig(
                        server_id=server.id,
                        command=server.command,
                        args=server.args or [],
                        env=server.env,
                    )
                )

    client_pool = ClientPool(server_configs)

    # Start downstream servers
    await client_pool.start()

    # Create discovery engine
    catalog = client_pool.get_catalog()
    discovery_engine = DiscoveryEngine(relations=None)
    discovery_engine.catalog = catalog

    # Get effect overrides from config (if any)
    effect_overrides: dict[str, EffectClass] = {}
    # TODO: Parse from configuration when available

    # Create gateway server
    gateway = GatewayServer(
        client_pool=client_pool,
        cloak_engine=cloak_engine,
        discovery_engine=discovery_engine,
        approval_manager=approval_manager,
        event_bus=event_bus,
        config_effect_overrides=effect_overrides,
    )

    # TODO: Start Control Room server when Dev A's implementation is available
    # For now, just print a placeholder message to stderr
    control_room_url = f"http://127.0.0.1:{control_room_port or 8765}/?token={token}"
    print(f"Control Room: {control_room_url}", file=sys.stderr)
    print(
        "(Control Room will be available after Dev A's implementation is merged)", file=sys.stderr
    )

    # Run gateway MCP server on stdio
    print("Cloakroom gateway ready", file=sys.stderr)

    try:
        await run_gateway_server(gateway)
    finally:
        # Cleanup
        log_event(logger, LogLevel.INFO, Event.CONFIGURATION_VALIDATED)
        await client_pool.stop()

    return 0

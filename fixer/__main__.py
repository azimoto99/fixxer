from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

from fixer.agent import OptimizerAgent
from fixer.config import load_config
from fixer.learning import LearningEngine
from fixer.logging_setup import configure_logging
from fixer.startup import get_startup_command, install_startup, remove_startup


def _add_runtime_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", default="config/default.json", help="Path to JSON config")
    parser.add_argument("--dry-run", action="store_true", help="Log actions without changing processes")
    parser.add_argument(
        "--mode",
        choices=["safe", "balanced", "aggressive"],
        help="Override mode from config",
    )
    parser.add_argument(
        "--learning-mode",
        action="store_true",
        help="Enable learning mode and suggestion snapshots",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fixer background optimizer")
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Run optimizer in console")
    _add_runtime_args(run_parser)
    run_parser.add_argument("--once", action="store_true", help="Run a single optimizer cycle")

    tray_parser = subparsers.add_parser("tray", help="Run optimizer with Windows system tray UI")
    _add_runtime_args(tray_parser)

    startup_parser = subparsers.add_parser("startup", help="Manage startup registration")
    startup_parser.add_argument("action", choices=["install", "remove", "status"])
    startup_parser.add_argument("--config", default="config/default.json", help="Path to JSON config")
    startup_parser.add_argument("--dry-run", action="store_true", help="Start tray in dry-run mode")
    startup_parser.add_argument(
        "--learning-mode",
        action="store_true",
        help="Enable learning mode at startup",
    )

    service_parser = subparsers.add_parser("service", help="Manage Windows service")
    service_parser.add_argument("action", choices=["install", "remove", "start", "stop", "restart", "status"])
    service_parser.add_argument("--config", default="config/default.json", help="Path to JSON config")
    service_parser.add_argument("--dry-run", action="store_true", help="Run service in dry-run mode")
    service_parser.add_argument(
        "--learning-mode",
        action="store_true",
        help="Enable learning mode for service runtime",
    )
    service_parser.add_argument(
        "--mode",
        choices=["safe", "balanced", "aggressive"],
        help="Override mode for service runtime",
    )
    service_parser.add_argument(
        "--manual-start",
        action="store_true",
        help="Install service with manual startup type",
    )

    return parser


def _normalized_argv(raw_argv: list[str]) -> list[str]:
    commands = {"run", "tray", "startup", "service"}
    if not raw_argv or raw_argv[0] not in commands:
        return ["run", *raw_argv]
    return raw_argv


def _default_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _resolve_config_path(raw_path: str) -> str:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        return str(candidate)

    if candidate.exists():
        return str(candidate.resolve())

    from_base = _default_base_dir() / candidate
    if from_base.exists():
        return str(from_base.resolve())

    return str(candidate)


def _resolve_runtime(args: argparse.Namespace):
    config_path = _resolve_config_path(args.config)
    config = load_config(config_path)

    mode = getattr(args, "mode", None)
    if mode:
        config = replace(config, mode=mode)

    learning_flag = bool(getattr(args, "learning_mode", False))
    learning_enabled = bool(learning_flag or config.learning.enabled)
    return config, learning_enabled


def _run_command(args: argparse.Namespace) -> None:
    config, learning_enabled = _resolve_runtime(args)
    configure_logging(config.log_level)

    learning = LearningEngine(config) if learning_enabled else None
    agent = OptimizerAgent(
        config=config,
        dry_run=args.dry_run,
        once=args.once,
        learning_engine=learning,
    )
    agent.run()


def _tray_command(args: argparse.Namespace) -> None:
    from fixer.tray import run_tray_app

    config, learning_enabled = _resolve_runtime(args)
    configure_logging(config.log_level)
    run_tray_app(config=config, dry_run=args.dry_run, learning_mode=learning_enabled)


def _startup_command(args: argparse.Namespace) -> None:
    if args.action == "install":
        config, learning_enabled = _resolve_runtime(args)
        configure_logging(config.log_level)
        command = install_startup(
            config_path=_resolve_config_path(args.config),
            dry_run=args.dry_run,
            learning_mode=learning_enabled,
        )
        print(f"Startup installed: {command}")
        return

    if args.action == "remove":
        removed = remove_startup()
        print("Startup entry removed" if removed else "Startup entry not found")
        return

    command = get_startup_command()
    if command:
        print(f"Startup installed: {command}")
    else:
        print("Startup not installed")


def _service_command(args: argparse.Namespace) -> None:
    from fixer.service import (
        install_service,
        remove_service,
        restart_service,
        service_status,
        start_service,
        stop_service,
    )

    if args.action == "install":
        config, learning_enabled = _resolve_runtime(args)
        configure_logging(config.log_level)
        result = install_service(
            config_path=_resolve_config_path(args.config),
            dry_run=args.dry_run,
            learning_mode=learning_enabled,
            mode_override=args.mode,
            auto_start=not args.manual_start,
        )
        print(f"Service {result}")
        return

    if args.action == "remove":
        print(f"Service {remove_service()}")
        return

    if args.action == "start":
        print(f"Service {start_service()}")
        return

    if args.action == "stop":
        print(f"Service {stop_service()}")
        return

    if args.action == "restart":
        print(f"Service {restart_service()}")
        return

    print(f"Service status: {service_status()}")


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    parsed = parser.parse_args(_normalized_argv(argv or sys.argv[1:]))

    if parsed.command == "run":
        _run_command(parsed)
        return

    if parsed.command == "tray":
        _tray_command(parsed)
        return

    if parsed.command == "startup":
        _startup_command(parsed)
        return

    if parsed.command == "service":
        _service_command(parsed)
        return

    parser.error("Unknown command")


if __name__ == "__main__":
    main()

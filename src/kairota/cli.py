from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from alembic import command
from alembic.config import Config

from kairota import __version__
from kairota.config import get_settings


def alembic_config() -> Config:
    return Config("alembic.ini")


def cmd_health(_args: argparse.Namespace) -> int:
    settings = get_settings()
    payload = {
        "status": "ok",
        "service": settings.app_name,
        "version": __version__,
    }
    print(json.dumps(payload, sort_keys=True))
    return 0


def cmd_db_upgrade(_args: argparse.Namespace) -> int:
    command.upgrade(alembic_config(), "head")
    return 0


def cmd_db_downgrade(_args: argparse.Namespace) -> int:
    command.downgrade(alembic_config(), "base")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kairota")
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    health = subparsers.add_parser("health", help="Print runtime health JSON.")
    health.set_defaults(func=cmd_health)

    db_upgrade = subparsers.add_parser("db-upgrade", help="Apply DB migrations.")
    db_upgrade.set_defaults(func=cmd_db_upgrade)

    db_downgrade = subparsers.add_parser(
        "db-downgrade",
        help="Downgrade DB migrations to base.",
    )
    db_downgrade.set_defaults(func=cmd_db_downgrade)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


__all__ = ["main"]

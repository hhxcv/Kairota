from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any
from uuid import uuid4

import uvicorn

from kairota.adapters.github.client import GitHubHttpClient
from kairota.config import DEFAULT_API_HOST, DEFAULT_API_PORT, get_settings
from kairota.contracts.schemas import ProjectCreate
from kairota.db import create_session_factory, ensure_database_ready
from kairota.services.errors import CommandBlockedError
from kairota.services.github_sync import sync_project_command
from kairota.services.projects import (
    get_project,
    list_projects,
    register_project_command,
)


def cmd_serve(args: argparse.Namespace) -> int:
    ensure_database_ready()
    uvicorn.run(
        "kairota.api.app:create_app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        factory=True,
    )
    return 0


def cmd_health(_args: argparse.Namespace) -> int:
    ensure_database_ready()
    print_json({"status": "ok", "service": "Kairota"})
    return 0


def cmd_project_register(args: argparse.Namespace) -> int:
    ensure_database_ready()
    factory = create_session_factory()
    with factory.begin() as session:
        project = register_project_command(
            session,
            command=ProjectCreate(remote=args.remote),
            idempotency_key=f"cli-register-{uuid4()}",
            actor="cli",
        )
    print_json(project.model_dump(mode="json"))
    return 0


def cmd_project_list(_args: argparse.Namespace) -> int:
    ensure_database_ready()
    factory = create_session_factory()
    with factory() as session:
        projects = list_projects(session)
    print_json([project.model_dump(mode="json") for project in projects])
    return 0


def cmd_project_show(args: argparse.Namespace) -> int:
    ensure_database_ready()
    factory = create_session_factory()
    with factory() as session:
        project = get_project(session, args.project_id)
    if project is None:
        print("Project not found.", file=sys.stderr)
        return 1
    print_json(project.model_dump(mode="json"))
    return 0


def cmd_project_sync(args: argparse.Namespace) -> int:
    settings = get_settings()
    ensure_database_ready(settings)
    factory = create_session_factory(settings)
    client = GitHubHttpClient.from_settings(settings)
    with factory.begin() as session:
        result = sync_project_command(
            session,
            project_id=args.project_id,
            idempotency_key=f"cli-sync-{uuid4()}",
            client=client,
        )
    print_json(result.model_dump(mode="json"))
    return 0 if result.error is None else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kairota",
        description="Run Kairota and manage GitHub projects.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve = subparsers.add_parser("serve", help="Start the local Kairota API.")
    serve.add_argument("--host", default=DEFAULT_API_HOST)
    serve.add_argument("--port", type=int, default=DEFAULT_API_PORT)
    serve.add_argument("--reload", action="store_true")
    serve.set_defaults(func=cmd_serve)

    health = subparsers.add_parser("health", help="Check local runtime readiness.")
    health.set_defaults(func=cmd_health)

    projects = subparsers.add_parser("projects", help="Manage GitHub projects.")
    project_commands = projects.add_subparsers(
        dest="project_command", required=True
    )
    register = project_commands.add_parser("register", help="Register owner/name.")
    register.add_argument("remote")
    register.set_defaults(func=cmd_project_register)

    project_list = project_commands.add_parser("list", help="List projects.")
    project_list.set_defaults(func=cmd_project_list)

    show = project_commands.add_parser("show", help="Show a project.")
    show.add_argument("project_id")
    show.set_defaults(func=cmd_project_show)

    sync = project_commands.add_parser("sync", help="Refresh GitHub Issues.")
    sync.add_argument("project_id")
    sync.set_defaults(func=cmd_project_sync)
    return parser


def print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, default=str))


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except CommandBlockedError as exc:
        print(f"{exc.reason_code}: {exc.explanation}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

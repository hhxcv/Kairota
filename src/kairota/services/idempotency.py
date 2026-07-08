from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from kairota.models.records import CommandRequest

JsonObject = dict[str, object]


class IdempotencyConflictError(ValueError):
    """Raised when an idempotency key is reused with a different payload."""


@dataclass(frozen=True)
class IdempotentCommandResult:
    body: JsonObject
    replayed: bool
    command_request_id: str


def payload_hash(payload: JsonObject) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def run_idempotent_command(
    session: Session,
    *,
    command_name: str,
    idempotency_key: str,
    payload: JsonObject,
    execute: Callable[[], JsonObject],
) -> IdempotentCommandResult:
    normalized_key = idempotency_key.strip()
    if not normalized_key:
        raise IdempotencyConflictError("Idempotency key must not be blank.")

    expected_hash = payload_hash(payload)
    command_request = session.scalar(
        select(CommandRequest)
        .where(
            CommandRequest.command_name == command_name,
            CommandRequest.idempotency_key == normalized_key,
        )
        .with_for_update()
    )
    if command_request is not None:
        if command_request.payload_hash != expected_hash:
            raise IdempotencyConflictError(
                "Idempotency key was already used with a different payload."
            )
        if command_request.status != "completed":
            raise IdempotencyConflictError(
                "Idempotency key is attached to an incomplete command."
            )
        return IdempotentCommandResult(
            body=command_request.response_body,
            replayed=True,
            command_request_id=command_request.id,
        )

    command_request = CommandRequest(
        command_name=command_name,
        idempotency_key=normalized_key,
        payload_hash=expected_hash,
        status="running",
        response_body={},
    )
    session.add(command_request)
    session.flush()

    body = execute()
    result_id = body.get("id") or body.get("cycle_id") or body.get("lease_id")
    command_request.status = "completed"
    command_request.response_body = body
    if isinstance(result_id, str):
        command_request.result_id = result_id
    session.flush()

    return IdempotentCommandResult(
        body=body,
        replayed=False,
        command_request_id=command_request.id,
    )

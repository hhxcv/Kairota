from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

from kairota.adapters.github.models import GitHubWebhookEvent

JsonObject = dict[str, Any]


class WebhookNormalizationError(ValueError):
    pass


def normalize_webhook_event(
    *, event_type: str, delivery_id: str, payload: bytes
) -> GitHubWebhookEvent:
    if event_type != "issues":
        raise WebhookNormalizationError("Only GitHub Issue events are supported.")
    try:
        document = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise WebhookNormalizationError("GitHub payload is not valid JSON.") from exc
    if not isinstance(document, dict):
        raise WebhookNormalizationError("GitHub payload must be a JSON object.")
    repository = require_object(document, "repository")
    issue = require_object(document, "issue")
    try:
        return GitHubWebhookEvent(
            delivery_id=delivery_id,
            event_type=event_type,
            action=optional_str(document.get("action")),
            project_name=str(repository["full_name"]),
            provider_repo_id=str(repository["id"]),
            issue_number=int(issue["number"]),
            payload_hash=payload_sha256(payload),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise WebhookNormalizationError(
            "GitHub Issue event is missing required repository or Issue fields."
        ) from exc


def verify_signature(
    *, secret: str, payload: bytes, signature_header: str | None
) -> bool:
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature_header.removeprefix("sha256="), expected)


def payload_sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def require_object(document: JsonObject, key: str) -> JsonObject:
    value = document.get(key)
    if not isinstance(value, dict):
        raise WebhookNormalizationError(
            f"GitHub payload field {key} must be an object."
        )
    return value


def optional_str(value: object) -> str | None:
    return str(value) if value not in (None, "") else None

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

from kairota.adapters.github.models import (
    GitHubSyncSnapshot,
    GitHubWebhookEvent,
)
from kairota.adapters.github.normalizers import (
    normalize_check_run,
    normalize_issue,
    normalize_pull_request,
    normalize_repository,
)

JsonObject = dict[str, Any]


class WebhookNormalizationError(ValueError):
    """Raised when a webhook event cannot be normalized safely."""


def payload_sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def verify_signature(
    *,
    secret: str,
    payload: bytes,
    signature_header: str | None,
) -> bool:
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = (
        "sha256="
        + hmac.new(
            secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()
    )
    return hmac.compare_digest(expected, signature_header)


def normalize_webhook_event(
    *,
    event_type: str,
    delivery_id: str,
    payload: bytes,
) -> GitHubWebhookEvent:
    document = json.loads(payload.decode("utf-8"))
    if not isinstance(document, dict):
        raise WebhookNormalizationError("Webhook payload must be a JSON object.")

    repository_payload = document.get("repository")
    if not isinstance(repository_payload, dict):
        raise WebhookNormalizationError("Webhook payload is missing repository.")
    repository = normalize_repository(repository_payload)
    action = optional_str(document.get("action"))
    external_id: str | None = None

    issues = []
    pull_requests = []
    checks = []

    if event_type == "issues":
        issue_payload = object_payload(document, "issue")
        issue = normalize_issue(issue_payload)
        external_id = str(issue.number)
        issues.append(issue)
    elif event_type == "pull_request":
        pr_payload = object_payload(document, "pull_request")
        pull_request = normalize_pull_request(pr_payload)
        external_id = str(pull_request.number)
        pull_requests.append(pull_request)
    elif event_type == "check_run":
        check_payload = object_payload(document, "check_run")
        check = normalize_check_run(check_payload)
        external_id = optional_str(check_payload.get("id"))
        if check is not None:
            checks.append(check)
    elif event_type == "issue_comment":
        issue_payload = object_payload(document, "issue")
        comment_payload = object_payload(document, "comment")
        external_id = optional_str(comment_payload.get("id"))
        if "pull_request" not in issue_payload:
            issues.append(normalize_issue(issue_payload))
    elif event_type == "status":
        external_id = optional_str(document.get("id") or document.get("sha"))
    else:
        raise WebhookNormalizationError(f"Unsupported GitHub event: {event_type}")

    snapshot = GitHubSyncSnapshot(
        repository=repository,
        issues=tuple(issues),
        pull_requests=tuple(pull_requests),
        checks=tuple(checks),
        reviews=(),
    )
    return GitHubWebhookEvent(
        event_type=event_type,
        delivery_id=delivery_id,
        action=action,
        external_id=external_id,
        payload_hash=payload_sha256(payload),
        snapshot=snapshot,
    )


def object_payload(document: JsonObject, key: str) -> JsonObject:
    value = document.get(key)
    if not isinstance(value, dict):
        raise WebhookNormalizationError(f"Webhook payload is missing {key}.")
    return value


def optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)

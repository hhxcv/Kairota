import hashlib
import hmac
import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session

from kairota.adapters.github.webhook import (
    normalize_webhook_event,
    payload_sha256,
    verify_signature,
)
from kairota.contracts.enums import EventStatus, RepositoryProvider
from kairota.models.records import ExternalRef, InboundEvent, Repository, WorkItem
from kairota.services.errors import CommandBlockedError
from kairota.services.github_sync import issue_external_id, process_github_webhook_event


@pytest.fixture()
def engine(tmp_path: Path) -> Iterator[Engine]:
    db_path = tmp_path / "kairota.sqlite"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")
    command.upgrade(config, "head")

    db_engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        yield db_engine
    finally:
        db_engine.dispose()


def issue_webhook_payload(title: str = "Imported issue") -> bytes:
    return json.dumps(
        {
            "action": "opened",
            "repository": {
                "id": 123,
                "full_name": "owner/repo",
                "default_branch": "main",
            },
            "issue": {
                "id": 456,
                "number": 7,
                "title": title,
                "html_url": "https://example.test/issues/7",
                "state": "open",
            },
        },
        sort_keys=True,
    ).encode("utf-8")


def issue_comment_webhook_payload(*, pull_request: bool = False) -> bytes:
    issue = {
        "id": 456,
        "number": 7,
        "title": "PR conversation" if pull_request else "Issue conversation",
        "html_url": "https://example.test/issues/7",
        "state": "open",
    }
    if pull_request:
        issue["pull_request"] = {"html_url": "https://example.test/pull/7"}
    return json.dumps(
        {
            "action": "created",
            "repository": {
                "id": 123,
                "full_name": "owner/repo",
                "default_branch": "main",
            },
            "issue": issue,
            "comment": {
                "id": 789,
                "html_url": "https://example.test/issues/7#issuecomment-789",
            },
        },
        sort_keys=True,
    ).encode("utf-8")


def test_webhook_signature_uses_hmac_sha256() -> None:
    payload = issue_webhook_payload()
    digest = hmac.new(b"secret", payload, hashlib.sha256).hexdigest()

    assert verify_signature(
        secret="secret",
        payload=payload,
        signature_header=f"sha256={digest}",
    )
    assert not verify_signature(
        secret="secret",
        payload=payload,
        signature_header="sha256=wrong",
    )


def test_webhook_processing_is_idempotent_and_does_not_store_payload(
    engine: Engine,
) -> None:
    payload = issue_webhook_payload()
    event = normalize_webhook_event(
        event_type="issues",
        delivery_id="delivery-1",
        payload=payload,
    )

    with Session(engine) as session, session.begin():
        first = process_github_webhook_event(session, event=event)
        second = process_github_webhook_event(session, event=event)

        assert not first.replayed
        assert second.replayed
        assert first.work_items_created == 1
        assert session.scalar(select(WorkItem.title)) == "Imported issue"
        inbound = session.scalar(select(InboundEvent))
        assert inbound is not None
        assert inbound.payload_hash == payload_sha256(payload)
        assert "Imported issue" not in inbound.payload_hash


def test_issue_comment_webhook_normalizes_issue_context() -> None:
    event = normalize_webhook_event(
        event_type="issue_comment",
        delivery_id="delivery-comment",
        payload=issue_comment_webhook_payload(),
    )

    assert event.external_id == "789"
    assert event.snapshot.issues[0].number == 7
    assert event.snapshot.reviews == ()


def test_pull_request_issue_comment_does_not_create_issue_snapshot() -> None:
    event = normalize_webhook_event(
        event_type="issue_comment",
        delivery_id="delivery-pr-comment",
        payload=issue_comment_webhook_payload(pull_request=True),
    )

    assert event.external_id == "789"
    assert event.snapshot.issues == ()
    assert event.snapshot.reviews == ()


def test_native_github_review_webhooks_are_not_supported() -> None:
    payload = json.dumps(
        {
            "action": "submitted",
            "repository": {
                "id": 123,
                "full_name": "owner/repo",
                "default_branch": "main",
            },
        }
    ).encode("utf-8")

    with pytest.raises(ValueError, match="Unsupported GitHub event"):
        normalize_webhook_event(
            event_type="pull_request_review",
            delivery_id="delivery-review",
            payload=payload,
        )
    with pytest.raises(ValueError, match="Unsupported GitHub event"):
        normalize_webhook_event(
            event_type="pull_request_review_thread",
            delivery_id="delivery-review-thread",
            payload=payload,
        )


def test_webhook_delivery_id_conflict_is_blocked(engine: Engine) -> None:
    first = normalize_webhook_event(
        event_type="issues",
        delivery_id="delivery-1",
        payload=issue_webhook_payload("First"),
    )
    second = normalize_webhook_event(
        event_type="issues",
        delivery_id="delivery-1",
        payload=issue_webhook_payload("Changed"),
    )

    with (
        pytest.raises(CommandBlockedError),
        Session(engine) as session,
        session.begin(),
    ):
        process_github_webhook_event(session, event=first)
        process_github_webhook_event(session, event=second)


def test_webhook_processing_failure_preserves_failed_inbound_event(
    engine: Engine,
) -> None:
    payload = issue_webhook_payload()
    event = normalize_webhook_event(
        event_type="issues",
        delivery_id="delivery-failed",
        payload=payload,
    )

    with Session(engine) as session, session.begin():
        repository = Repository(
            provider=RepositoryProvider.GITHUB.value,
            provider_repo_id="123",
            name="owner/repo",
            default_branch="main",
            sync_status="unknown",
        )
        session.add(repository)
        session.flush()
        session.add(
            ExternalRef(
                provider=RepositoryProvider.GITHUB.value,
                external_type="issue",
                external_id=issue_external_id(repository.id, 7),
                repository_id=repository.id,
            )
        )
        session.flush()

        result = process_github_webhook_event(session, event=event)
        inbound = session.scalar(
            select(InboundEvent).where(InboundEvent.id == result.inbound_event_id)
        )

        assert result.status == "failed"
        assert inbound is not None
        assert inbound.status == EventStatus.FAILED.value
        assert inbound.error == "IntegrityError"

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from kairota.adapters.github.models import GitHubClient
from kairota.adapters.github.webhook import (
    WebhookNormalizationError,
    normalize_webhook_event,
    verify_signature,
)
from kairota.api.deps import get_github_client, get_session
from kairota.contracts.enums import WorkItemStatus
from kairota.contracts.schemas import (
    BlockedCommandResponse,
    ClaimWorkItemCommand,
    ClaimWorkItemRead,
    LeaseExpiryRead,
    LeaseHeartbeatCommand,
    LeaseHeartbeatRead,
    QueueSummaryRead,
    QueueWorkbenchRead,
    RepositorySyncRead,
    SchedulerCycleCreate,
    SchedulerCycleRead,
    WorkerRunCloseCommand,
    WorkerRunCreateCommand,
    WorkerRunHeartbeatCommand,
    WorkerRunRead,
    WorkerRunReportCommand,
    WorkItemCreate,
    WorkItemRead,
)
from kairota.services.errors import CommandBlockedError
from kairota.services.github_sync import (
    process_github_webhook_event,
    sync_repository_command,
)
from kairota.services.idempotency import IdempotencyConflictError
from kairota.services.queue_workbench import queue_workbench
from kairota.services.scheduler_cycles import (
    claim_work_item_command,
    expire_stale_leases_command,
    heartbeat_lease_command,
    run_scheduler_cycle_command,
)
from kairota.services.work_items import (
    create_work_item_command,
    get_work_item,
    list_work_items,
    queue_summary,
)
from kairota.services.worker_runs import (
    close_worker_run_command,
    create_worker_run_command,
    get_worker_run,
    heartbeat_worker_run_command,
    report_worker_run_command,
)

router = APIRouter()

IdempotencyHeader = Annotated[str | None, Header(alias="Idempotency-Key")]
SessionDependency = Annotated[Session, Depends(get_session)]
GitHubClientDependency = Annotated[GitHubClient, Depends(get_github_client)]


@router.get("/work-items", response_model=tuple[WorkItemRead, ...])
def api_list_work_items(
    session: SessionDependency,
    status: WorkItemStatus | None = None,
) -> tuple[WorkItemRead, ...]:
    return list_work_items(session, status=status)


@router.get("/work-items/{work_item_id}", response_model=WorkItemRead)
def api_get_work_item(
    work_item_id: str,
    session: SessionDependency,
) -> WorkItemRead:
    work_item = get_work_item(session, work_item_id)
    if work_item is None:
        raise HTTPException(status_code=404, detail="Work item not found.")
    return work_item


@router.post("/work-items", response_model=WorkItemRead)
def api_create_work_item(
    command: WorkItemCreate,
    session: SessionDependency,
    idempotency_key: IdempotencyHeader = None,
) -> WorkItemRead | JSONResponse:
    if not idempotency_key:
        return blocked_response(
            400,
            "missing_idempotency_key",
            "POST /work-items requires an Idempotency-Key header.",
        )
    try:
        with session.begin():
            return create_work_item_command(
                session,
                command=command,
                idempotency_key=idempotency_key,
                actor="api",
            )
    except IdempotencyConflictError as exc:
        return blocked_response(409, "idempotency_conflict", str(exc))
    except CommandBlockedError as exc:
        return blocked_response(409, exc.reason_code, exc.explanation, exc.details)


@router.get("/queue/summary", response_model=QueueSummaryRead)
def api_queue_summary(session: SessionDependency) -> QueueSummaryRead:
    return queue_summary(session)


@router.get("/queue/workbench", response_model=QueueWorkbenchRead)
def api_queue_workbench(session: SessionDependency) -> QueueWorkbenchRead:
    return queue_workbench(session)


@router.post("/scheduler/cycles", response_model=SchedulerCycleRead)
def api_run_scheduler_cycle(
    command: SchedulerCycleCreate,
    session: SessionDependency,
    idempotency_key: IdempotencyHeader = None,
) -> SchedulerCycleRead | JSONResponse:
    if not idempotency_key:
        return blocked_response(
            400,
            "missing_idempotency_key",
            "POST /scheduler/cycles requires an Idempotency-Key header.",
        )
    try:
        with session.begin():
            return run_scheduler_cycle_command(
                session,
                command=command,
                idempotency_key=idempotency_key,
            )
    except IdempotencyConflictError as exc:
        return blocked_response(409, "idempotency_conflict", str(exc))


@router.post("/work-items/{work_item_id}/claim", response_model=ClaimWorkItemRead)
def api_claim_work_item(
    work_item_id: str,
    command: ClaimWorkItemCommand,
    session: SessionDependency,
    idempotency_key: IdempotencyHeader = None,
) -> ClaimWorkItemRead | JSONResponse:
    if not idempotency_key:
        return blocked_response(
            400,
            "missing_idempotency_key",
            "POST /work-items/{id}/claim requires an Idempotency-Key header.",
        )
    try:
        with session.begin():
            result = claim_work_item_command(
                session,
                work_item_id=work_item_id,
                command=command,
                idempotency_key=idempotency_key,
            )
    except IdempotencyConflictError as exc:
        return blocked_response(409, "idempotency_conflict", str(exc))

    if not result.claimed:
        return blocked_response(
            409,
            str(result.reason or "blocked"),
            result.explanation or "Work item claim was blocked.",
            {
                "work_item_id": result.work_item_id,
                "conflict_keys": result.conflict_keys,
            },
        )
    return result


@router.post("/leases/{lease_id}/heartbeat", response_model=LeaseHeartbeatRead)
def api_heartbeat_lease(
    lease_id: str,
    command: LeaseHeartbeatCommand,
    session: SessionDependency,
    idempotency_key: IdempotencyHeader = None,
) -> LeaseHeartbeatRead | JSONResponse:
    if not idempotency_key:
        return blocked_response(
            400,
            "missing_idempotency_key",
            "POST /leases/{id}/heartbeat requires an Idempotency-Key header.",
        )
    try:
        with session.begin():
            result = heartbeat_lease_command(
                session,
                lease_id=lease_id,
                command=command,
                idempotency_key=idempotency_key,
            )
    except IdempotencyConflictError as exc:
        return blocked_response(409, "idempotency_conflict", str(exc))

    if not result.refreshed:
        return blocked_response(
            409,
            "lease_heartbeat_blocked",
            result.explanation or "Lease heartbeat was blocked.",
            {"lease_id": result.lease_id},
        )
    return result


@router.post("/reconcile/leases/expire", response_model=LeaseExpiryRead)
def api_expire_stale_leases(
    session: SessionDependency,
    idempotency_key: IdempotencyHeader = None,
) -> LeaseExpiryRead | JSONResponse:
    if not idempotency_key:
        return blocked_response(
            400,
            "missing_idempotency_key",
            "POST /reconcile/leases/expire requires an Idempotency-Key header.",
        )
    try:
        with session.begin():
            return expire_stale_leases_command(
                session,
                idempotency_key=idempotency_key,
            )
    except IdempotencyConflictError as exc:
        return blocked_response(409, "idempotency_conflict", str(exc))


@router.get("/worker-runs/{worker_run_id}", response_model=WorkerRunRead)
def api_get_worker_run(
    worker_run_id: str,
    session: SessionDependency,
) -> WorkerRunRead:
    worker_run = get_worker_run(session, worker_run_id)
    if worker_run is None:
        raise HTTPException(status_code=404, detail="Worker run not found.")
    return worker_run


@router.post("/worker-runs", response_model=WorkerRunRead)
def api_create_worker_run(
    command: WorkerRunCreateCommand,
    session: SessionDependency,
    idempotency_key: IdempotencyHeader = None,
) -> WorkerRunRead | JSONResponse:
    if not idempotency_key:
        return blocked_response(
            400,
            "missing_idempotency_key",
            "POST /worker-runs requires an Idempotency-Key header.",
        )
    try:
        with session.begin():
            return create_worker_run_command(
                session,
                command=command,
                idempotency_key=idempotency_key,
                actor="api",
            )
    except IdempotencyConflictError as exc:
        return blocked_response(409, "idempotency_conflict", str(exc))
    except CommandBlockedError as exc:
        return blocked_response(409, exc.reason_code, exc.explanation, exc.details)


@router.post("/worker-runs/{worker_run_id}/heartbeat", response_model=WorkerRunRead)
def api_heartbeat_worker_run(
    worker_run_id: str,
    command: WorkerRunHeartbeatCommand,
    session: SessionDependency,
    idempotency_key: IdempotencyHeader = None,
) -> WorkerRunRead | JSONResponse:
    if not idempotency_key:
        return blocked_response(
            400,
            "missing_idempotency_key",
            "POST /worker-runs/{id}/heartbeat requires an Idempotency-Key header.",
        )
    try:
        with session.begin():
            return heartbeat_worker_run_command(
                session,
                worker_run_id=worker_run_id,
                command=command,
                idempotency_key=idempotency_key,
                actor="api",
            )
    except IdempotencyConflictError as exc:
        return blocked_response(409, "idempotency_conflict", str(exc))
    except CommandBlockedError as exc:
        return blocked_response(409, exc.reason_code, exc.explanation, exc.details)


@router.post("/worker-runs/{worker_run_id}/report", response_model=WorkerRunRead)
def api_report_worker_run(
    worker_run_id: str,
    command: WorkerRunReportCommand,
    session: SessionDependency,
    idempotency_key: IdempotencyHeader = None,
) -> WorkerRunRead | JSONResponse:
    if not idempotency_key:
        return blocked_response(
            400,
            "missing_idempotency_key",
            "POST /worker-runs/{id}/report requires an Idempotency-Key header.",
        )
    try:
        with session.begin():
            return report_worker_run_command(
                session,
                worker_run_id=worker_run_id,
                command=command,
                idempotency_key=idempotency_key,
                actor="api",
            )
    except IdempotencyConflictError as exc:
        return blocked_response(409, "idempotency_conflict", str(exc))
    except CommandBlockedError as exc:
        return blocked_response(409, exc.reason_code, exc.explanation, exc.details)


@router.post("/worker-runs/{worker_run_id}/close", response_model=WorkerRunRead)
def api_close_worker_run(
    worker_run_id: str,
    command: WorkerRunCloseCommand,
    session: SessionDependency,
    idempotency_key: IdempotencyHeader = None,
) -> WorkerRunRead | JSONResponse:
    if not idempotency_key:
        return blocked_response(
            400,
            "missing_idempotency_key",
            "POST /worker-runs/{id}/close requires an Idempotency-Key header.",
        )
    try:
        with session.begin():
            return close_worker_run_command(
                session,
                worker_run_id=worker_run_id,
                command=command,
                idempotency_key=idempotency_key,
                actor="api",
            )
    except IdempotencyConflictError as exc:
        return blocked_response(409, "idempotency_conflict", str(exc))
    except CommandBlockedError as exc:
        return blocked_response(409, exc.reason_code, exc.explanation, exc.details)


@router.post("/repositories/{repository_id}/sync", response_model=RepositorySyncRead)
def api_sync_repository(
    repository_id: str,
    session: SessionDependency,
    github_client: GitHubClientDependency,
    idempotency_key: IdempotencyHeader = None,
) -> RepositorySyncRead | JSONResponse:
    if not idempotency_key:
        return blocked_response(
            400,
            "missing_idempotency_key",
            "POST /repositories/{id}/sync requires an Idempotency-Key header.",
        )
    try:
        with session.begin():
            return sync_repository_command(
                session,
                repository_id=repository_id,
                idempotency_key=idempotency_key,
                client=github_client,
            )
    except IdempotencyConflictError as exc:
        return blocked_response(409, "idempotency_conflict", str(exc))
    except CommandBlockedError as exc:
        return blocked_response(409, exc.reason_code, exc.explanation, exc.details)


@router.post("/webhooks/github", response_model=RepositorySyncRead)
async def api_github_webhook(
    request: Request,
    session: SessionDependency,
    event_type: Annotated[str | None, Header(alias="X-GitHub-Event")] = None,
    delivery_id: Annotated[str | None, Header(alias="X-GitHub-Delivery")] = None,
    signature: Annotated[str | None, Header(alias="X-Hub-Signature-256")] = None,
) -> RepositorySyncRead | JSONResponse:
    payload = await request.body()
    settings = request.app.state.settings
    if not event_type or not delivery_id:
        return blocked_response(
            400,
            "missing_github_headers",
            "GitHub webhook event and delivery headers are required.",
        )
    if settings.github_webhook_secret and not verify_signature(
        secret=settings.github_webhook_secret,
        payload=payload,
        signature_header=signature,
    ):
        return blocked_response(
            401,
            "invalid_github_signature",
            "GitHub webhook signature verification failed.",
        )
    try:
        event = normalize_webhook_event(
            event_type=event_type,
            delivery_id=delivery_id,
            payload=payload,
        )
        with session.begin():
            return process_github_webhook_event(session, event=event)
    except WebhookNormalizationError as exc:
        return blocked_response(400, "webhook_normalization_failed", str(exc))
    except CommandBlockedError as exc:
        return blocked_response(409, exc.reason_code, exc.explanation, exc.details)


def blocked_response(
    status_code: int,
    reason_code: str,
    explanation: str,
    details: dict[str, object] | None = None,
) -> JSONResponse:
    body = BlockedCommandResponse(
        reason_code=reason_code,
        explanation=explanation,
        details=details or {},
    )
    return JSONResponse(status_code=status_code, content=body.model_dump(mode="json"))

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from kairota.adapters.github.models import GitHubClient
from kairota.adapters.github.webhook import (
    WebhookNormalizationError,
    normalize_webhook_event,
    verify_signature,
)
from kairota.api.deps import get_github_client, get_session
from kairota.contracts.enums import SchedulingState
from kairota.contracts.schemas import (
    BlockedCommandResponse,
    IssueAnalysisCommand,
    IssueClaimCommand,
    IssuePageRead,
    IssueReleaseCommand,
    ManagedIssueRead,
    ProjectCreate,
    ProjectRead,
    ProjectSyncRead,
    ProjectUpdate,
)
from kairota.services.errors import CommandBlockedError
from kairota.services.github_sync import process_webhook, sync_project_command
from kairota.services.idempotency import IdempotencyConflictError
from kairota.services.issues import (
    analyze_issue_command,
    claim_issue_command,
    get_issue_read,
    list_issues,
    release_issue_command,
)
from kairota.services.projects import (
    get_project,
    list_projects,
    register_project_command,
    update_project_command,
)

router = APIRouter()

IdempotencyHeader = Annotated[str | None, Header(alias="Idempotency-Key")]
SessionDependency = Annotated[Session, Depends(get_session)]
GitHubClientDependency = Annotated[GitHubClient, Depends(get_github_client)]
ProjectFilter = Annotated[list[str] | None, Query(alias="project_id")]
StateFilter = Annotated[list[SchedulingState] | None, Query(alias="state")]


@router.get("/projects", response_model=tuple[ProjectRead, ...])
def api_list_projects(session: SessionDependency) -> tuple[ProjectRead, ...]:
    return list_projects(session)


@router.post("/projects", response_model=ProjectRead)
def api_register_project(
    command: ProjectCreate,
    session: SessionDependency,
    idempotency_key: IdempotencyHeader = None,
) -> ProjectRead | JSONResponse:
    if not idempotency_key:
        return missing_key("POST /projects")
    try:
        with session.begin():
            return register_project_command(
                session,
                command=command,
                idempotency_key=idempotency_key,
                actor="api",
            )
    except (CommandBlockedError, IdempotencyConflictError) as exc:
        return command_error(exc)


@router.get("/projects/{project_id}", response_model=ProjectRead)
def api_get_project(project_id: str, session: SessionDependency) -> ProjectRead:
    project = get_project(session, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return project


@router.patch("/projects/{project_id}", response_model=ProjectRead)
def api_update_project(
    project_id: str,
    command: ProjectUpdate,
    session: SessionDependency,
    idempotency_key: IdempotencyHeader = None,
) -> ProjectRead | JSONResponse:
    if not idempotency_key:
        return missing_key("PATCH /projects/{id}")
    try:
        with session.begin():
            return update_project_command(
                session,
                project_id=project_id,
                command=command,
                idempotency_key=idempotency_key,
                actor="api",
            )
    except (CommandBlockedError, IdempotencyConflictError) as exc:
        return command_error(exc)


@router.post("/projects/{project_id}/sync", response_model=ProjectSyncRead)
def api_sync_project(
    project_id: str,
    session: SessionDependency,
    client: GitHubClientDependency,
    idempotency_key: IdempotencyHeader = None,
) -> ProjectSyncRead | JSONResponse:
    if not idempotency_key:
        return missing_key("POST /projects/{id}/sync")
    try:
        with session.begin():
            return sync_project_command(
                session,
                project_id=project_id,
                idempotency_key=idempotency_key,
                client=client,
            )
    except (CommandBlockedError, IdempotencyConflictError) as exc:
        return command_error(exc)


@router.get("/issues", response_model=IssuePageRead)
def api_list_issues(
    session: SessionDependency,
    project_id: ProjectFilter = None,
    state: StateFilter = None,
    query: str | None = None,
    claimable: bool | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> IssuePageRead:
    return list_issues(
        session,
        project_ids=tuple(project_id or ()),
        states=tuple(state or ()),
        query=query,
        claimable=claimable,
        page=page,
        page_size=page_size,
        sync_stale_after_seconds=sync_stale_after(session),
    )


@router.get("/issues/{issue_id}", response_model=ManagedIssueRead)
def api_get_issue(issue_id: str, session: SessionDependency) -> ManagedIssueRead:
    issue = get_issue_read(
        session,
        issue_id,
        sync_stale_after_seconds=sync_stale_after(session),
    )
    if issue is None:
        raise HTTPException(status_code=404, detail="Issue not found.")
    return issue


@router.put("/issues/{issue_id}/analysis", response_model=ManagedIssueRead)
def api_analyze_issue(
    issue_id: str,
    command: IssueAnalysisCommand,
    session: SessionDependency,
    idempotency_key: IdempotencyHeader = None,
) -> ManagedIssueRead | JSONResponse:
    if not idempotency_key:
        return missing_key("PUT /issues/{id}/analysis")
    try:
        with session.begin():
            return analyze_issue_command(
                session,
                issue_id=issue_id,
                command=command,
                idempotency_key=idempotency_key,
                actor="main-ai",
                sync_stale_after_seconds=sync_stale_after(session),
            )
    except (CommandBlockedError, IdempotencyConflictError) as exc:
        return command_error(exc)


@router.post("/issues/{issue_id}/claim", response_model=ManagedIssueRead)
def api_claim_issue(
    issue_id: str,
    command: IssueClaimCommand,
    session: SessionDependency,
    idempotency_key: IdempotencyHeader = None,
) -> ManagedIssueRead | JSONResponse:
    if not idempotency_key:
        return missing_key("POST /issues/{id}/claim")
    try:
        with session.begin():
            return claim_issue_command(
                session,
                issue_id=issue_id,
                command=command,
                idempotency_key=idempotency_key,
                actor="main-ai",
                sync_stale_after_seconds=sync_stale_after(session),
            )
    except (CommandBlockedError, IdempotencyConflictError) as exc:
        return command_error(exc)


@router.post("/issues/{issue_id}/release", response_model=ManagedIssueRead)
def api_release_issue(
    issue_id: str,
    command: IssueReleaseCommand,
    session: SessionDependency,
    idempotency_key: IdempotencyHeader = None,
) -> ManagedIssueRead | JSONResponse:
    if not idempotency_key:
        return missing_key("POST /issues/{id}/release")
    try:
        with session.begin():
            return release_issue_command(
                session,
                issue_id=issue_id,
                command=command,
                idempotency_key=idempotency_key,
                actor="main-ai",
                sync_stale_after_seconds=sync_stale_after(session),
            )
    except (CommandBlockedError, IdempotencyConflictError) as exc:
        return command_error(exc)


@router.post("/webhooks/github", response_model=ProjectSyncRead)
async def api_github_webhook(
    request: Request,
    session: SessionDependency,
    client: GitHubClientDependency,
    github_event: Annotated[str | None, Header(alias="X-GitHub-Event")] = None,
    delivery_id: Annotated[str | None, Header(alias="X-GitHub-Delivery")] = None,
    signature: Annotated[str | None, Header(alias="X-Hub-Signature-256")] = None,
) -> ProjectSyncRead | JSONResponse | Response:
    if not github_event or not delivery_id:
        return blocked_response(
            400,
            "missing_webhook_headers",
            "GitHub event and delivery headers are required.",
        )
    payload = await request.body()
    secret = request.app.state.settings.github_webhook_secret
    if not secret:
        return blocked_response(
            503,
            "webhook_not_configured",
            "GitHub webhook verification is not configured.",
        )
    if not verify_signature(
        secret=secret, payload=payload, signature_header=signature
    ):
        return blocked_response(
            401, "invalid_webhook_signature", "GitHub signature is invalid."
        )
    if github_event == "ping":
        return Response(status_code=204)
    try:
        event = normalize_webhook_event(
            event_type=github_event,
            delivery_id=delivery_id,
            payload=payload,
        )
        with session.begin():
            return process_webhook(session, event=event, client=client)
    except WebhookNormalizationError as exc:
        return blocked_response(400, "invalid_webhook", str(exc))
    except CommandBlockedError as exc:
        return command_error(exc)


def sync_stale_after(session: Session) -> int:
    request = session.info.get("request")
    if isinstance(request, Request):
        return int(request.app.state.settings.sync_stale_after_seconds)
    return 300


def missing_key(endpoint: str) -> JSONResponse:
    return blocked_response(
        400,
        "missing_idempotency_key",
        f"{endpoint} requires an Idempotency-Key header.",
    )


def command_error(
    exc: CommandBlockedError | IdempotencyConflictError,
) -> JSONResponse:
    if isinstance(exc, IdempotencyConflictError):
        return blocked_response(409, "idempotency_conflict", str(exc))
    return blocked_response(409, exc.reason_code, exc.explanation, exc.details)


def blocked_response(
    status_code: int,
    reason_code: str,
    explanation: str,
    details: dict[str, object] | None = None,
) -> JSONResponse:
    payload = BlockedCommandResponse(
        reason_code=reason_code,
        explanation=explanation,
        details=details or {},
    )
    return JSONResponse(
        status_code=status_code,
        content=payload.model_dump(mode="json"),
    )

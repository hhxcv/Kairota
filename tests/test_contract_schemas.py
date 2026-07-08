from datetime import UTC, datetime

from kairota.contracts.enums import (
    AutonomyMode,
    LeaseStatus,
    RiskLevel,
    WorkItemStatus,
    WorkType,
)
from kairota.contracts.schemas import LeaseRead, WorkItemRead


def test_work_item_contract_serializes_enum_values() -> None:
    payload = WorkItemRead(
        id="wi-1",
        title="Implement schema",
        status=WorkItemStatus.READY,
        priority=10,
        risk=RiskLevel.HIGH,
        work_type=WorkType.IMPLEMENTATION,
        autonomy_mode=AutonomyMode.AI_ASSISTED,
    ).model_dump(mode="json")

    assert payload["status"] == "ready"
    assert payload["risk"] == "high"
    assert payload["work_type"] == "implementation"
    assert payload["autonomy_mode"] == "ai_assisted"


def test_lease_contract_preserves_fencing_token() -> None:
    expires_at = datetime(2026, 1, 1, tzinfo=UTC)
    payload = LeaseRead(
        id="lease-1",
        work_item_id="wi-1",
        owner="worker-slot-1",
        status=LeaseStatus.ACTIVE,
        fencing_token="token-1",
        expires_at=expires_at,
    ).model_dump(mode="json")

    assert payload["status"] == "active"
    assert payload["fencing_token"] == "token-1"
    assert payload["expires_at"] == "2026-01-01T00:00:00Z"

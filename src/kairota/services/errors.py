from __future__ import annotations

from dataclasses import dataclass, field

JsonObject = dict[str, object]


@dataclass(frozen=True)
class CommandBlockedError(Exception):
    reason_code: str
    explanation: str
    details: JsonObject = field(default_factory=dict)

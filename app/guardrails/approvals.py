"""The human checkpoint: a proposed "scrap" or "escalate" waits here until a person decides.

The decision is stored as a new event, never as an edit, and nothing is ever carried out by this service.
"""

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

PENDING = "pending_approval"
OVERDUE = "overdue"


def photo_fingerprint(photo: bytes | None) -> str | None:
    return hashlib.sha256(photo).hexdigest() if photo else None


def proposed_action_now(record: dict[str, Any], events: list[dict[str, Any]], due_minutes: float) -> dict[str, Any] | None:
    """The proposed action with its current status, worked out from the events."""
    proposed = record["result"].get("proposed_action")
    if proposed is None:
        return None
    decided = next((event for event in events if event["type"] == "approval"), None)
    if decided:
        payload = decided["payload"]
        return {
            **proposed,
            "status": payload["decision"],
            "decided_by": payload["approver"],
            "decided_at": decided["created_at"],
            "note": payload["note"],
        }
    due_at = datetime.fromisoformat(record["created_at"]) + timedelta(minutes=due_minutes)
    status = OVERDUE if datetime.now(timezone.utc) > due_at else PENDING
    return {**proposed, "status": status, "due_at": due_at.isoformat()}

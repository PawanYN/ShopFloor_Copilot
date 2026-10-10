from typing import Any, Literal

from pydantic import BaseModel, Field


class InspectResponse(BaseModel):
    transaction_id: str
    conversation_id: str
    answer: str
    decision: str
    defect_category: str | None
    ocr_text: str | None
    rules: list[dict[str, Any]]
    # Set when the result is "scrap" or "escalate". It is a proposal only and waits for a person.
    proposed_action: dict[str, Any] | None
    config: dict[str, Any]
    trace: list[dict[str, Any]]
    latency_seconds: float


class FeedbackRequest(BaseModel):
    transaction_id: str
    score: Literal[0, 1]


class FeedbackResponse(BaseModel):
    transaction_id: str
    score: int
    recorded: bool
    reward: float
    # What the learning loop changed, or null when the answer used no passage search.
    learning: dict[str, Any] | None


class ApprovalRequest(BaseModel):
    transaction_id: str
    decision: Literal["approved", "rejected"]
    approver: str = Field(min_length=1)
    note: str = ""


class TransactionResponse(BaseModel):
    transaction_id: str
    created_at: str
    inputs: dict[str, Any]
    answer: str
    decision: str
    defect_category: str | None
    ocr_text: str | None
    rules: list[dict[str, Any]]
    # Status is pending_approval, overdue, approved or rejected.
    proposed_action: dict[str, Any] | None
    config: dict[str, Any]
    trace: list[dict[str, Any]]
    latency_seconds: float
    events: list[dict[str, Any]]

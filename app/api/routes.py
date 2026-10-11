import logging
import time
import uuid

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from app import config
from app.agent.loop import run_turn
from app.api.schemas import (
    ApprovalRequest,
    FeedbackRequest,
    FeedbackResponse,
    InspectResponse,
    TransactionResponse,
)
from app.guardrails.approvals import photo_fingerprint, proposed_action_now
from app.learning.bandit import NO_IMAGE, reward_for

router = APIRouter()
log = logging.getLogger("uvicorn.error")


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/inspect", response_model=InspectResponse)
def inspect(
    request: Request,
    query: str = Form(...),
    work_order_id: str | None = Form(None),
    conversation_id: str | None = Form(None),
    image: UploadFile | None = File(None),
) -> InspectResponse:
    started = time.perf_counter()
    state = request.app.state
    transaction_id = uuid.uuid4().hex
    conversation_id = conversation_id or uuid.uuid4().hex

    conversation = state.conversations.get(conversation_id)
    fields = {}
    if image is not None:
        # A new photo replaces the earlier one, and its earlier result no longer applies.
        photo, vision = image.file.read(), None
        fields.update(image=photo, image_filename=image.filename)
    else:
        photo, vision = conversation["image"], conversation["vision"]
    log.info(
        "inspect %s: query=%r, photo=%s, work order=%s",
        transaction_id,
        query,
        image.filename if image else ("from earlier in the conversation" if photo else "none"),
        work_order_id or conversation["work_order_id"] or "none",
    )

    result = run_turn(
        state.model_client,
        state.answer_model,
        state.retrieve,
        query,
        image=photo,
        vision=vision,
        work_order_id=work_order_id or conversation["work_order_id"],
        history=conversation["messages"],
        choose_top_k=state.bandit.choose,
        max_steps=config.MAX_AGENT_STEPS,
        time_limit=config.LATENCY_CEILING_SECONDS,
    )

    seen = result.vision or {}
    run_config = {
        "answer_model": state.answer_model,
        "embedding_model": config.EMBEDDING_MODEL,
        "ocr_engine": "tesseract",
        "rag_top_k": result.top_k,
        "rag_top_k_choice": result.top_k_choice,
        "model_calls": result.model_calls,
        "prompt_tokens": result.prompt_tokens,
        "completion_tokens": result.completion_tokens,
    }
    latency = round(time.perf_counter() - started, 3)
    state.store.add_transaction(
        {
            "id": transaction_id,
            "inputs": {
                "query": query,
                "work_order_id": work_order_id,
                "image_filename": image.filename if image else conversation["image_filename"],
                # Proves later which photo was looked at; the photo itself is kept with the conversation.
                "image_sha256": photo_fingerprint(photo),
                "conversation_id": conversation_id,
            },
            "defect_category": seen.get("defect_category"),
            "ocr_text": seen.get("ocr_text"),
            "config": run_config,
            "trace": result.trace,
            "answer": result.answer,
            "result": {
                "decision": result.decision,
                "reason": result.reason,
                "rules": result.rules,
                "proposed_action": result.proposed_action,
            },
            "latency_seconds": latency,
        }
    )
    state.conversations.update(
        conversation_id,
        [
            {"role": "worker", "text": query},
            {"role": "assistant", "text": result.answer, "decision": result.decision, "transaction_id": transaction_id},
        ],
        {**fields, "vision": result.vision, "work_order_id": result.work_order_id},
    )
    log.info(
        "inspect %s: decision=%s (%s) after %d steps and %d model calls, %.1fs",
        transaction_id,
        result.decision,
        result.reason,
        len(result.trace),
        result.model_calls,
        latency,
    )

    return InspectResponse(
        transaction_id=transaction_id,
        conversation_id=conversation_id,
        answer=result.answer,
        decision=result.decision,
        defect_category=seen.get("defect_category"),
        ocr_text=seen.get("ocr_text"),
        rules=result.rules,
        proposed_action=result.proposed_action,
        config=run_config,
        trace=result.trace,
        latency_seconds=latency,
    )


@router.post("/feedback", response_model=FeedbackResponse)
def feedback(request: Request, body: FeedbackRequest) -> FeedbackResponse:
    store = request.app.state.store
    record = store.get_transaction(body.transaction_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Unknown transaction_id")
    if any(event["type"] == "feedback" for event in store.list_events(body.transaction_id)):
        raise HTTPException(status_code=409, detail="Feedback was already given for this answer")

    reward = reward_for(body.score, record["latency_seconds"])
    store.add_event(body.transaction_id, "feedback", {"score": body.score, "reward": reward})

    # The learning loop is updated here, in the same call. Answers that searched no passages teach it nothing.
    learning = None
    top_k = record["config"].get("rag_top_k")
    if top_k is not None:
        learned_for = record["defect_category"] or NO_IMAGE
        value = request.app.state.bandit.update(learned_for, top_k, reward, body.transaction_id)
        learning = {"state": learned_for, "rag_top_k": top_k, "reward": reward, "score_after": round(value, 3)}
    log.info("feedback %s: score=%d, reward=%.2f, learning=%s", body.transaction_id, body.score, reward, learning)
    return FeedbackResponse(
        transaction_id=body.transaction_id, score=body.score, recorded=True, reward=reward, learning=learning
    )


def _transaction(store, transaction_id: str) -> TransactionResponse:
    record = store.get_transaction(transaction_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Unknown transaction_id")
    events = store.list_events(transaction_id)
    result = record.pop("result")
    return TransactionResponse(
        transaction_id=record.pop("id"),
        decision=result["decision"],
        rules=result["rules"],
        proposed_action=proposed_action_now({**record, "result": result}, events, config.APPROVAL_DUE_MINUTES),
        events=events,
        **record,
    )


@router.get("/transactions/{transaction_id}", response_model=TransactionResponse)
def get_transaction(request: Request, transaction_id: str) -> TransactionResponse:
    return _transaction(request.app.state.store, transaction_id)


@router.post("/approvals", response_model=TransactionResponse)
def approve(request: Request, body: ApprovalRequest) -> TransactionResponse:
    """A supervisor approves or rejects a proposed action. The decision is recorded; nothing is executed."""
    store = request.app.state.store
    current = _transaction(store, body.transaction_id)
    if current.proposed_action is None:
        raise HTTPException(status_code=409, detail="This answer has no proposed action to approve")
    if current.proposed_action["status"] in ("approved", "rejected"):
        raise HTTPException(status_code=409, detail="This proposed action was already decided")

    store.add_event(
        body.transaction_id, "approval", {"decision": body.decision, "approver": body.approver, "note": body.note}
    )
    log.info("approval %s: %s by %s", body.transaction_id, body.decision, body.approver)
    return _transaction(store, body.transaction_id)


@router.get("/audit/verify")
def verify_audit(request: Request) -> dict:
    """Recompute the fingerprint chain of the audit tables and report whether any row was changed or removed."""
    return request.app.state.store.verify_chain()

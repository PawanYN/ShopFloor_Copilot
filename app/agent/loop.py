"""The agent loop: the model picks the next tool, code runs it and writes down the step.

The record of steps is written here, as each step happens (decision 4.9). The model
supplies only its choice and its reason.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from app.agent.work_orders import check_work_order_status
from app.knowledge.answer import NEEDS_APPROVAL, Answer, answer_information, check_measurement, search_text
from app.knowledge.store import Hit
from app.learning.bandit import NO_IMAGE
from app.llm import ModelClient, ModelTimeout
from app.vision.inspect import inspect_image

log = logging.getLogger("uvicorn.error")

TOOLS = ("check_photo", "search_rules", "check_work_order", "send_to_person", "ask_worker")

STEP_SCHEMA = {
    "type": "object",
    "properties": {
        "why": {"type": "string"},
        "tool": {"type": "string", "enum": list(TOOLS)},
        "input": {"type": "string"},
        "check_part": {"type": "boolean"},
    },
    "required": ["why", "tool", "input", "check_part"],
}

PLANNER_PROMPT = """You plan the next step for ShopFloor Copilot, an assistant for line workers at a machining plant.

Choose exactly one tool for the next step. Reply with JSON:
- "why": one short sentence giving your reason for this step.
- "tool": one of the tools below.
- "input": what the tool needs (see each tool).
- "check_part": only used by search_rules; otherwise false.

Tools:
- "check_photo": looks at the photo the worker sent. It reports the defect type, a measurement, and the ID stamped on the part. "input": "". Use it when a photo was sent, it has not been checked yet, and the worker's request is about the part.
- "check_work_order": looks up a work order's status, rework count and priority. "input": the work order ID, for example "WO-12345". Use it when a work order ID is known and its status matters for the request.
- "search_rules": searches the plant's SOP documents and gives the worker the final answer. "input": what to look up, in a few words. Set "check_part" to true when the worker wants to know whether the inspected part is acceptable or what to do with it; set it to false for a general question about rules, limits or contacts.
- "ask_worker": asks the worker one question and waits for the reply. "input": the question. Use it only when it is unclear what the worker wants.
- "send_to_person": hands the case to a supervisor or quality lead. "input": the reason. Use it when you are unsure and a wrong answer could harm a part.

"check_photo" and "check_work_order" only gather facts; they do not answer the worker. After them, use "search_rules" to give the worker the answer.
Use the facts and the steps already taken. Never repeat a step that has already been done."""


@dataclass
class AgentResult:
    answer: str
    decision: str  # accept, rework, scrap, escalate, inform, no_exact_answer or ask_worker
    trace: list[dict[str, Any]]
    vision: dict | None = None
    work_order_id: str | None = None
    rules: list[dict[str, Any]] = field(default_factory=list)
    reason: str = ""
    top_k: int | None = None
    top_k_choice: str | None = None  # best_known or trying_another
    proposed_action: dict | None = None
    model_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0


def _vision_summary(vision: dict) -> str:
    measurement = vision["measurement"]
    direction = f" {measurement['direction']}" if measurement.get("direction") else ""
    part_id = vision["part_id"] or f"unreadable (read as {vision['ocr_text']!r})"
    return (
        f"defect type {vision['defect_category']}, {measurement['name']} {measurement['value']} mm{direction}, "
        f"confidence {vision['confidence']}, part ID {part_id}"
    )


def _work_order_summary(record: dict) -> str:
    if not record["found"]:
        return f"work order {record['work_order_id']} was not found"
    priority = "priority order" if record["priority"] else "not a priority order"
    return f"{record['work_order_id']}: status {record['status']}, reworked {record['rework_count']} time(s), {priority}"


def _planner_input(message: str, history: list[dict], has_photo: bool, facts: dict, trace: list[dict]) -> str:
    talk = "\n".join(f"{item['role']}: {item['text']}" for item in history[-6:]) or "(this is the first message)"
    photo = "no photo was sent"
    if has_photo:
        photo = f"checked: {_vision_summary(facts['vision'])}" if facts["vision"] else "a photo was sent and has NOT been checked yet"
    order = facts["work_order_id"] or "none known"
    if facts["work_order"]:
        order = _work_order_summary(facts["work_order"])
    steps = "\n".join(f"{step['step']}. {step['tool']}({step['input']}) -> {step['result']}" for step in trace) or "(none yet)"
    return (
        f"## Conversation so far\n{talk}\n\n## Worker's message now\n{message}\n\n"
        f"## Facts\nphoto: {photo}\nwork order: {order}\n\n## Steps already taken for this message\n{steps}"
    )


def run_turn(
    client: ModelClient,
    model: str,
    retrieve: Callable[[str, int], list[Hit]],
    message: str,
    *,
    image: bytes | None = None,
    vision: dict | None = None,
    work_order_id: str | None = None,
    history: list[dict] | None = None,
    choose_top_k: Callable[[str], tuple[int, str]],
    max_steps: int = 5,
    time_limit: float | None = None,
) -> AgentResult:
    deadline = time.monotonic() + time_limit if time_limit else None
    chosen: dict[str, Any] = {}

    def time_left() -> float | None:
        return None if deadline is None else deadline - time.monotonic()

    facts = {"vision": vision, "work_order_id": work_order_id, "work_order": None}
    gathered: set[tuple[str, str]] = set()
    trace: list[dict[str, Any]] = []
    usage = {"model_calls": 0, "prompt_tokens": 0, "completion_tokens": 0}

    def count(reply) -> None:
        usage["model_calls"] += 1
        usage["prompt_tokens"] += reply.prompt_tokens
        usage["completion_tokens"] += reply.completion_tokens

    def finish(
        answer: str,
        decision: str,
        reason: str,
        rules: list[dict] | None = None,
        top_k: int | None = None,
        top_k_choice: str | None = None,
    ) -> AgentResult:
        proposed = None
        if decision in NEEDS_APPROVAL:
            # Never executed here: a person must approve it first.
            proposed = {"action": decision, "status": "pending_approval", "reason": reason}
        return AgentResult(
            answer=answer,
            decision=decision,
            trace=trace,
            vision=facts["vision"],
            work_order_id=facts["work_order_id"],
            rules=rules or [],
            reason=reason,
            top_k=top_k,
            top_k_choice=top_k_choice,
            proposed_action=proposed,
            **usage,
        )

    def fall_back() -> AgentResult:
        """The model passed the time limit: reply with the matching SOP passages, written by no model (decision 6.8)."""
        seen = facts["vision"]
        if not chosen:
            chosen["top_k"], chosen["choice"] = choose_top_k(seen["defect_category"] if seen else NO_IMAGE)
        hits = retrieve(search_text(message, seen), chosen["top_k"])
        log.warning("time limit of %g seconds passed: sending the ready-made reply", time_limit)
        trace.append(
            {
                "step": len(trace) + 1,
                "tool": "ready_made_reply",
                "input": "",
                "why": f"the model did not answer within the {time_limit:g} second limit, and the slow call is not tried again",
                "result": f"returned the top {chosen['top_k']} SOP passages without a model-written answer",
                "seconds": 0.0,
            }
        )
        found = f" The camera found: {_vision_summary(seen)}." if seen else ""
        passages = "\n\n".join(
            f"{hit.metadata['document']} section {hit.metadata['section']} (revision {hit.metadata['revision']}): "
            f"{hit.text.split(chr(10) + chr(10), 1)[-1]}"
            for hit in hits
        )
        rules = [
            {
                "document": hit.metadata["document"],
                "section": hit.metadata["section"],
                "revision": hit.metadata["revision"],
                "title": hit.metadata["section_title"],
                "limits": [],
            }
            for hit in hits
        ]
        answer = (
            f"The assistant is taking too long, so here are the rules that match your question.{found}\n\n{passages}\n\n"
            "No decision has been made for you. If you are unsure, ask your supervisor."
        )
        return finish(answer, "ready_made_reply", "time_limit", rules, chosen["top_k"], chosen["choice"])

    for number in range(1, max_steps + 1):
        started = time.perf_counter()
        log.info("step %d: asking %s which tool to use next", number, model)
        try:
            reply = client.chat_json(
                model,
                PLANNER_PROMPT,
                _planner_input(message, history or [], image is not None, facts, trace),
                STEP_SCHEMA,
                time_left(),
            )
        except ModelTimeout:
            return fall_back()
        except Exception as error:
            log.exception("step %d: the planning model failed", number)
            trace.append({"step": number, "tool": None, "input": "", "why": "", "result": f"the planning model failed: {error}", "seconds": 0.0})
            return finish("I could not work this out. Please ask your supervisor.", "escalate", "planner_failed")
        count(reply)
        step = reply.data
        tool, tool_input = step["tool"], step["input"].strip()
        entry = {"step": number, "tool": tool, "input": tool_input, "why": step["why"].strip()}
        trace.append(entry)
        log.info("step %d: chose %s(%s) because: %s", number, tool, tool_input, entry["why"])

        def done(result: str) -> None:
            entry["result"] = result
            entry["seconds"] = round(time.perf_counter() - started, 2)
            log.info("step %d: %s -> %s (%.2fs)", number, tool, result, entry["seconds"])

        if tool in ("check_photo", "check_work_order") and (tool, tool_input) in gathered:
            done("this was already done and its result is in the facts; use search_rules now to answer the worker")
            continue
        gathered.add((tool, tool_input))

        if tool == "check_photo":
            if image is None:
                done("no photo was sent, so there is nothing to check")
            elif facts["vision"]:
                done("the photo was already checked")
            else:
                try:
                    facts["vision"] = inspect_image(image).to_dict()
                except ValueError as error:
                    done(f"the photo could not be used: {error}")
                    continue
                if facts["vision"]["part_id"] and not facts["work_order_id"]:
                    facts["work_order_id"] = facts["vision"]["part_id"]
                done(_vision_summary(facts["vision"]))

        elif tool == "check_work_order":
            wanted = tool_input or facts["work_order_id"] or ""
            if not wanted:
                done("no work order ID is known")
                continue
            facts["work_order"] = check_work_order_status(wanted)
            if facts["work_order"]["found"]:
                facts["work_order_id"] = facts["work_order"]["work_order_id"]
            done(_work_order_summary(facts["work_order"]))

        elif tool == "ask_worker":
            done("asked the worker and stopped to wait for the reply")
            return finish(tool_input, "ask_worker", "model_choice")

        elif tool == "send_to_person":
            done("proposed that a person decides")
            return finish(f"This should be decided by a person. Reason: {tool_input}", "escalate", "model_choice")

        else:  # search_rules
            seen = facts["vision"]
            if step["check_part"] and seen is None and image is not None:
                done("the photo has not been checked yet, so the part cannot be judged; check the photo first")
                continue
            check_part = step["check_part"] and seen is not None
            top_k, choice = choose_top_k(seen["defect_category"] if seen else NO_IMAGE)
            chosen["top_k"], chosen["choice"] = top_k, choice
            # For a part check the search is built from the worker's words and the defect seen, not from the
            # model's wording, so the right limits are found whatever the model typed.
            query = search_text(message, seen) if check_part else (tool_input or message)
            hits = retrieve(query, top_k)
            log.info("step %d: found %d passages (top %d, %s); asking %s for the answer", number, len(hits), top_k, choice, model)
            try:
                if check_part:
                    answer = check_measurement(client, model, hits, seen, time_left())
                else:
                    answer = answer_information(client, model, message, hits, seen, facts["work_order"], time_left())
            except ModelTimeout:
                done(f"searched top {top_k} passages ({choice}); the model ran out of time")
                return fall_back()
            except Exception as error:
                log.exception("step %d: the answering model failed", number)
                done(f"the answering model failed: {error}")
                return finish("I could not work this out. Please ask your supervisor.", "escalate", "answer_failed")
            usage["model_calls"] += 1
            usage["prompt_tokens"] += answer.usage["prompt_tokens"]
            usage["completion_tokens"] += answer.usage["completion_tokens"]
            answer = _apply_work_order(answer, facts["work_order"])
            cited = ", ".join(f"{rule['document']} {rule['section']}" for rule in answer.rules) or "no rule"
            done(f"searched top {top_k} passages ({choice}); {answer.kind}: {answer.decision} ({answer.reason}); cited {cited}")
            return finish(answer.message, answer.decision, answer.reason, answer.rules, top_k, choice)

    return finish(
        f"I could not work this out in {max_steps} steps. Please ask your supervisor.", "escalate", "step_limit"
    )


def _apply_work_order(answer: Answer, work_order: dict | None) -> Answer:
    """A part that was already reworked is not sent to rework again by the system; a person decides."""
    if answer.decision == "rework" and work_order and work_order.get("found") and work_order["rework_count"] >= 1:
        answer.decision, answer.reason, answer.needs_approval = "escalate", "already_reworked", True
        answer.message += (
            f" However, work order {work_order['work_order_id']} shows this part has already been reworked "
            f"{work_order['rework_count']} time(s), so the rework rules must be checked by a person. This is escalated."
        )
    return answer

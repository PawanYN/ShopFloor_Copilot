from pathlib import Path

from app.agent.loop import run_turn
from tests.helpers import INFO_REPLY, LIMITS_REPLY, ScriptedClient, retrieve, scratch, step

SCRATCH_PHOTO = Path("data/images/surface_scratch_03.png").read_bytes()  # a 30 mm scratch, ID WO-29628


def turn(replies: list, message: str = "Is this OK?", **options):
    client = ScriptedClient(replies)
    result = run_turn(client, "m", retrieve, message, choose_top_k=lambda state: (3, "best_known"), **options)
    return result, client


def test_photo_then_limit_check_records_each_step_as_it_happens():
    result, _ = turn([step("check_photo"), step("search_rules", "scratch limits", True), LIMITS_REPLY], image=SCRATCH_PHOTO)

    assert result.decision == "scrap"
    assert result.proposed_action == {"action": "scrap", "status": "pending_approval", "reason": "limit"}
    assert result.vision["defect_category"] == "surface_scratch" and result.work_order_id == "WO-29628"
    assert [(s["step"], s["tool"]) for s in result.trace] == [(1, "check_photo"), (2, "search_rules")]
    assert all(s["why"] and s["result"] and "seconds" in s for s in result.trace)
    assert "defect type surface_scratch" in result.trace[0]["result"]
    assert (result.top_k, result.model_calls) == (3, 3)


def test_the_model_may_answer_without_looking_at_the_photo():
    result, _ = turn([step("search_rules", "scratch limit"), INFO_REPLY], image=SCRATCH_PHOTO)
    assert (result.decision, result.vision, result.proposed_action) == ("inform", None, None)
    assert result.rules[0]["section"] == "1.2"


def test_judging_the_part_before_checking_the_photo_is_sent_back():
    replies = [step("search_rules", "limits", True), step("check_photo"), step("search_rules", "limits", True), LIMITS_REPLY]
    result, client = turn(replies, image=SCRATCH_PHOTO)
    assert "check the photo first" in result.trace[0]["result"]
    assert result.decision == "scrap" and len(result.trace) == 3
    # The next planning prompt shows the step that was already taken.
    assert "check the photo first" in client.prompts[1]


def test_running_out_of_steps_is_escalated():
    result, _ = turn([step("check_work_order", "WO-19651")] * 5)
    assert (result.decision, result.reason) == ("escalate", "step_limit")
    assert len(result.trace) == 5 and result.proposed_action["status"] == "pending_approval"
    assert "ask your supervisor" in result.answer
    # The lookup ran once; the repeats were refused and the model was told what to do instead.
    assert "status in inspection" in result.trace[0]["result"]
    assert all("already done" in s["result"] for s in result.trace[1:])


def test_a_part_check_searches_with_the_defect_seen_not_the_models_wording():
    searched = []

    def recording_retrieve(text, top_k):
        searched.append(text)
        return retrieve(text, top_k)

    client = ScriptedClient([step("search_rules", "WO-64962 acceptable", True), LIMITS_REPLY])
    run_turn(client, "m", recording_retrieve, "Is it OK?", vision=scratch(15.0), choose_top_k=lambda state: (3, "best_known"))
    assert searched == ["Is it OK? (surface scratch limits)"]


def test_the_model_can_ask_the_worker_or_hand_over_to_a_person():
    result, _ = turn([step("ask_worker", "What do you want to know about this photo?")], image=SCRATCH_PHOTO)
    assert (result.decision, result.answer, result.proposed_action) == ("ask_worker", "What do you want to know about this photo?", None)

    result, _ = turn([step("send_to_person", "I am not sure which rule applies.")])
    assert (result.decision, result.reason) == ("escalate", "model_choice")
    assert result.proposed_action["action"] == "escalate" and "not sure" in result.answer


def test_a_part_already_reworked_is_not_sent_to_rework_again():
    replies = [step("check_work_order", "WO-64962"), step("search_rules", "scratch limits", True), LIMITS_REPLY]
    result, _ = turn(replies, vision=scratch(15.0))
    assert (result.decision, result.reason) == ("escalate", "already_reworked")
    assert "reworked 1 time(s)" in result.trace[0]["result"] and "already been reworked" in result.answer


def test_unknown_work_order_bad_photo_and_model_failure_are_handled():
    result, _ = turn([step("check_work_order", "WO-00000"), step("check_photo"), step("search_rules"), INFO_REPLY], image=b"not-an-image")
    assert "was not found" in result.trace[0]["result"]
    assert "could not be used" in result.trace[1]["result"]
    assert result.decision == "inform"

    result, _ = turn([RuntimeError("model down")])
    assert (result.decision, result.reason) == ("escalate", "planner_failed")

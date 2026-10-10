from app.knowledge.answer import answer_question, decide_measurement, information_prompt, limits_prompt
from app.knowledge.store import Hit
from app.llm import ModelReply


def hit(document: str, section: str, text: str = "rule text", revision: str = "4") -> Hit:
    metadata = {"document": document, "section": section, "revision": revision, "section_title": "Title"}
    return Hit(f"{document}#{section}", text, metadata, 0.1)


def scratch(value: float) -> dict:
    return {"defect_category": "surface_scratch", "measurement": {"name": "length_mm", "value": value}, "confidence": 0.9}


def limit(over, up_to, decision, when="any") -> dict:
    return {"when": when, "over": over, "up_to": up_to, "decision": decision}


def rule(document: str, section: str, limits: list[dict]) -> dict:
    return {"document": document, "section": section, "revision": "4", "title": "Title", "limits": limits}


SPEC = [limit(None, 10, "accept"), limit(10, 25, "rework"), limit(25, None, "scrap")]
SCRAP_RULES = [limit(10, 20, "rework"), limit(20, None, "scrap")]


class FakeClient:
    def __init__(self, data: dict) -> None:
        self.data = data

    def chat_json(self, model, system, user, schema, timeout=None) -> ModelReply:
        self.user = user
        return ModelReply(self.data, prompt_tokens=100, completion_tokens=20, seconds=0.5)


def test_code_compares_the_measurement_with_the_limits():
    for value, expected in [(6.0, "accept"), (9.4, "accept"), (10.6, "rework"), (24.4, "rework"), (25.6, "scrap")]:
        decision, message, reason = decide_measurement([rule("SOP-01", "1.2", SPEC)], scratch(value))
        assert (decision, reason) == (expected, "limit"), value
        assert "SOP-01 section 1.2 (revision 4)" in message


def test_a_reading_within_camera_error_of_a_limit_is_escalated():
    for value in (9.5, 9.9, 10.0, 10.1, 10.5, 24.6, 25.4):
        decision, message, reason = decide_measurement([rule("SOP-01", "1.2", SPEC)], scratch(value))
        assert (decision, reason) == ("escalate", "near_limit"), value
        assert "caliper" in message


def test_documents_that_disagree_are_escalated_with_both_cited():
    rules = [rule("SOP-01", "1.2", SPEC), rule("SOP-02", "2.2", SCRAP_RULES)]
    decision, message, reason = decide_measurement(rules, scratch(22.0))
    assert (decision, reason) == ("escalate", "conflict")
    assert "SOP-01 section 1.2" in message and "SOP-02 section 2.2" in message

    # The same two documents agree at 15 mm, so there is no conflict there.
    assert decide_measurement(rules, scratch(15.0))[::2] == ("rework", "limit")


def test_direction_selects_the_size_limit():
    limits = [limit(None, 1.0, "accept"), limit(1.0, 3.0, "rework", "oversize"), limit(1.0, None, "scrap", "undersize"), limit(3.0, None, "scrap")]

    def size(value: float, direction: str) -> dict:
        measurement = {"name": "deviation_mm", "value": value, "direction": direction}
        return {"defect_category": "dimensional_deviation", "measurement": measurement, "confidence": 1.0}

    assert decide_measurement([rule("SOP-01", "1.4", limits)], size(2.0, "oversize"))[0] == "rework"
    assert decide_measurement([rule("SOP-01", "1.4", limits)], size(2.0, "undersize"))[0] == "scrap"
    assert decide_measurement([rule("SOP-01", "1.4", limits)], size(0.3, "undersize"))[0] == "accept"


def test_any_escalate_rule_wins_and_no_matching_limit_is_escalated():
    rules = [rule("SOP-01", "1.3", [limit(None, None, "escalate")]), rule("SOP-02", "2.3", [limit(None, None, "scrap")])]
    assert decide_measurement(rules, scratch(5.0))[::2] == ("escalate", "rule_escalation")
    assert decide_measurement([rule("SOP-02", "2.2", SCRAP_RULES)], scratch(5.0))[::2] == ("escalate", "no_limit")


def test_measurement_answer_uses_code_and_drops_citations_not_retrieved():
    client = FakeClient(
        {
            "rules": [
                {"passage": "P1", "defect_type": "surface scratch", "limits": SPEC},
                {"passage": "P2", "defect_type": "crack", "limits": [limit(None, None, "escalate")]},
                {"passage": "P9", "defect_type": "surface scratch", "limits": [limit(None, None, "accept")]},
            ]
        }
    )
    hits = [hit("SOP-01", "1.2"), hit("SOP-01", "1.3")]
    answer = answer_question(client, "m", "Is this OK?", hits, scratch(30.0))
    # The crack rule is ignored for a scratch, and a passage label that was never given is not used.
    assert (answer.kind, answer.decision, answer.needs_approval) == ("measurement_check", "scrap", True)
    assert [r["section"] for r in answer.rules] == ["1.2"]
    assert answer.invalid_citations == ["P9"]
    assert answer.usage["prompt_tokens"] == 100
    # The model is asked only to copy limits: it is never shown the measured value.
    assert "30.0" not in client.user and "surface scratch" in client.user


def information(answered: bool, person: bool, message: str) -> dict:
    return {
        "answered_by_passages": answered,
        "passages_used": ["P1"],
        "must_go_to_a_person": person,
        "message": message,
    }


def test_information_answer_keeps_the_models_sentence():
    hits = [hit("SOP-03", "3.2")]
    answer = answer_question(FakeClient(information(True, False, " Sanjay Patil. ")), "m", "Who is the Quality Lead at night?", hits)
    assert (answer.kind, answer.decision, answer.message, answer.needs_approval) == ("information", "inform", "Sanjay Patil.", False)

    answer = answer_question(FakeClient(information(True, True, "Escalate.")), "m", "q", hits)
    assert (answer.decision, answer.needs_approval) == ("escalate", True)


def test_a_question_the_passages_do_not_answer_is_marked_as_such():
    answer = answer_question(FakeClient(information(False, False, "I do not have an exact rule.")), "m", "Dent limit?", [hit("SOP-03", "3.2")])
    assert (answer.kind, answer.decision, answer.needs_approval) == ("no_exact_answer", "no_exact_answer", False)
    assert [r["section"] for r in answer.rules] == ["3.2"]


def test_prompts_have_labelled_sections():
    hits = [hit("SOP-01", "1.2", "Scratch text")]
    prompt = limits_prompt(hits, scratch(12.0))
    assert prompt.index("## Defect type") < prompt.index("## SOP passages")
    assert "[P1] SOP-01 section 1.2, revision 4" in prompt and "its length in mm" in prompt

    prompt = information_prompt("Is this OK?", hits, None)
    assert prompt.index("## Camera result") < prompt.index("## SOP passages") < prompt.index("## Question")
    assert "No photo was supplied." in prompt

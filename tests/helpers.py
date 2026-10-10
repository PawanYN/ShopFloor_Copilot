from app.knowledge.store import Hit
from app.llm import ModelReply


class ScriptedClient:
    """Stands in for the language model: returns the given replies in order."""

    def __init__(self, replies: list) -> None:
        self.replies = list(replies)
        self.prompts: list[str] = []

    def chat_json(self, model, system, user, schema, timeout=None) -> ModelReply:
        self.prompts.append(user)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return ModelReply(reply, prompt_tokens=10, completion_tokens=5, seconds=0.1)


def step(tool: str, tool_input: str = "", check_part: bool = False, why: str = "because it is needed") -> dict:
    return {"why": why, "tool": tool, "input": tool_input, "check_part": check_part}


def limit(over, up_to, decision, when="any") -> dict:
    return {"when": when, "over": over, "up_to": up_to, "decision": decision}


SCRATCH_LIMITS = [limit(None, 10, "accept"), limit(10, 25, "rework"), limit(25, None, "scrap")]
LIMITS_REPLY = {"rules": [{"passage": "P1", "defect_type": "surface scratch", "limits": SCRATCH_LIMITS}]}
INFO_REPLY = {
    "answered_by_passages": True,
    "passages_used": ["P1"],
    "must_go_to_a_person": False,
    "message": "A scratch up to 10 mm long is acceptable.",
}

HITS = [
    Hit(
        "SOP-01#1.2",
        "A scratch up to 10 mm long is acceptable.",
        {"document": "SOP-01", "section": "1.2", "revision": "4", "section_title": "Surface scratch limits"},
        0.1,
    )
]


def retrieve(text: str, top_k: int) -> list[Hit]:
    return HITS


def scratch(value: float) -> dict:
    return {
        "defect_category": "surface_scratch",
        "measurement": {"name": "length_mm", "value": value},
        "confidence": 0.9,
        "part_id": "WO-64962",
        "ocr_text": "WO-64962",
    }

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.storage.conversations import MemoryConversationStore
from tests.helpers import INFO_REPLY, LIMITS_REPLY, ScriptedClient, retrieve, step

ANSWER = [step("search_rules", "scratch limit"), INFO_REPLY]


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.db")


@pytest.fixture
def make_client(db_path):
    def make(replies: list) -> TestClient:
        model = ScriptedClient(replies)
        app = create_app(db_path, MemoryConversationStore(), model, retrieve)
        app.state.bandit.epsilon = 0  # no random tries, so the tests are repeatable
        client = TestClient(app)
        client.model = model
        return client

    return make


def test_inspect_answers_and_can_be_replayed(make_client):
    client = make_client(ANSWER)
    created = client.post("/inspect", data={"query": "What scratch length is allowed?", "work_order_id": "WO-19651"})
    assert created.status_code == 200
    body = created.json()
    assert (body["answer"], body["decision"], body["proposed_action"]) == (INFO_REPLY["message"], "inform", None)
    assert body["rules"][0]["document"] == "SOP-01"
    assert (body["config"]["rag_top_k"], body["config"]["rag_top_k_choice"]) == (1, "best_known")
    assert body["config"]["model_calls"] == 2
    assert [s["tool"] for s in body["trace"]] == ["search_rules"]

    stored = client.get(f"/transactions/{body['transaction_id']}").json()
    assert stored["inputs"]["query"] == "What scratch length is allowed?"
    assert stored["inputs"]["conversation_id"] == body["conversation_id"]
    assert (stored["answer"], stored["trace"], stored["config"]) == (body["answer"], body["trace"], body["config"])


def test_a_conversation_remembers_the_photo_and_what_was_said(make_client):
    client = make_client(
        [
            step("ask_worker", "What do you want to know about this photo?"),
            step("check_photo"),
            step("search_rules", "scratch limits", True),
            LIMITS_REPLY,
        ]
    )
    photo = Path("data/images/surface_scratch_03.png").read_bytes()
    first = client.post("/inspect", data={"query": "check this"}, files={"image": ("part.png", photo, "image/png")}).json()
    assert first["decision"] == "ask_worker" and first["defect_category"] is None

    second = client.post("/inspect", data={"query": "is the scratch acceptable?", "conversation_id": first["conversation_id"]}).json()
    assert second["conversation_id"] == first["conversation_id"]
    assert (second["defect_category"], second["ocr_text"], second["decision"]) == ("surface_scratch", "WO-29628", "scrap")
    assert second["proposed_action"]["status"] == "pending_approval"
    # The planner was shown the earlier exchange.
    assert "worker: check this" in client.model.prompts[1]
    assert "assistant: What do you want to know about this photo?" in client.model.prompts[1]


def test_feedback_is_stored_as_a_new_event(make_client):
    client = make_client(ANSWER)
    transaction_id = client.post("/inspect", data={"query": "q"}).json()["transaction_id"]

    response = client.post("/feedback", json={"transaction_id": transaction_id, "score": 1})
    assert response.status_code == 200

    body = response.json()
    assert body["learning"]["state"] == "no_image" and body["learning"]["rag_top_k"] == 1
    assert body["reward"] == body["learning"]["reward"] == body["learning"]["score_after"] <= 10

    events = client.get(f"/transactions/{transaction_id}").json()["events"]
    assert [(e["type"], e["payload"]["score"]) for e in events] == [("feedback", 1)]

    # One thumbs up or down per answer.
    assert client.post("/feedback", json={"transaction_id": transaction_id, "score": 0}).status_code == 409


def test_feedback_changes_what_the_system_chooses_next(make_client):
    client = make_client(ANSWER * 4)
    used = []
    for score in (0, 0, 0):
        body = client.post("/inspect", data={"query": "q"}).json()
        used.append(body["config"]["rag_top_k"])
        client.post("/feedback", json={"transaction_id": body["transaction_id"], "score": score})
    # Each setting is tried once before any is trusted.
    assert used == [1, 3, 5]

    sheet = client.app.state.bandit.values("no_image")
    assert all(entry["count"] == 1 and entry["value"] <= 0 for entry in sheet.values())


def test_feedback_rejects_unknown_transaction_and_bad_score(make_client):
    client = make_client(ANSWER)
    assert client.post("/feedback", json={"transaction_id": "missing", "score": 1}).status_code == 404

    transaction_id = client.post("/inspect", data={"query": "q"}).json()["transaction_id"]
    assert client.post("/feedback", json={"transaction_id": transaction_id, "score": 5}).status_code == 422


def test_unknown_transaction_returns_404(make_client):
    assert make_client([]).get("/transactions/missing").status_code == 404


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE transactions SET answer = 'changed'",
        "DELETE FROM transactions",
        "UPDATE events SET payload = '{}'",
        "DELETE FROM events",
        "UPDATE learning_updates SET reward = 10",
        "DELETE FROM learning_updates",
    ],
)
def test_audit_tables_reject_edits_and_deletes(make_client, db_path, statement):
    client = make_client(ANSWER)
    transaction_id = client.post("/inspect", data={"query": "q"}).json()["transaction_id"]
    client.post("/feedback", json={"transaction_id": transaction_id, "score": 0})

    conn = sqlite3.connect(db_path)
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        conn.execute(statement)
    conn.close()

import hashlib
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import config
from app.agent.loop import run_turn
from app.llm import ModelTimeout
from app.main import create_app
from app.storage.conversations import MemoryConversationStore
from tests.helpers import INFO_REPLY, ScriptedClient, retrieve, scratch, step

ESCALATE = [step("send_to_person", "I am not sure which rule applies.")]
ANSWER = [step("search_rules", "scratch limit"), INFO_REPLY]


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.db")


@pytest.fixture
def make_client(db_path):
    def make(replies: list) -> TestClient:
        app = create_app(db_path, MemoryConversationStore(), ScriptedClient(replies), retrieve)
        app.state.bandit.epsilon = 0
        return TestClient(app)

    return make


def test_a_proposed_action_waits_until_a_supervisor_decides(make_client):
    client = make_client(ESCALATE)
    proposed = client.post("/inspect", data={"query": "what now?"}).json()
    assert proposed["proposed_action"]["status"] == "pending_approval"
    transaction_id = proposed["transaction_id"]
    assert client.get(f"/transactions/{transaction_id}").json()["proposed_action"]["status"] == "pending_approval"

    decision = {"transaction_id": transaction_id, "decision": "approved", "approver": "Anita Deshmukh", "note": "Seen at station 4"}
    approved = client.post("/approvals", json=decision)
    assert approved.status_code == 200
    action = approved.json()["proposed_action"]
    assert (action["status"], action["decided_by"], action["note"]) == ("approved", "Anita Deshmukh", "Seen at station 4")
    # Stored as a new event, not as an edit of the original record.
    assert [event["type"] for event in approved.json()["events"]] == ["approval"]

    assert client.post("/approvals", json={**decision, "decision": "rejected"}).status_code == 409


def test_approval_is_refused_when_there_is_nothing_to_approve(make_client):
    client = make_client(ANSWER)
    transaction_id = client.post("/inspect", data={"query": "q"}).json()["transaction_id"]
    body = {"transaction_id": transaction_id, "decision": "approved", "approver": "Anita Deshmukh"}
    assert client.post("/approvals", json=body).status_code == 409
    assert client.post("/approvals", json={**body, "transaction_id": "missing"}).status_code == 404
    assert client.post("/approvals", json={**body, "approver": ""}).status_code == 422


def test_an_unanswered_proposal_becomes_overdue(make_client, monkeypatch):
    client = make_client(ESCALATE)
    transaction_id = client.post("/inspect", data={"query": "what now?"}).json()["transaction_id"]

    monkeypatch.setattr(config, "APPROVAL_DUE_MINUTES", 0)
    assert client.get(f"/transactions/{transaction_id}").json()["proposed_action"]["status"] == "overdue"

    # An overdue proposal can still be decided by a person.
    body = {"transaction_id": transaction_id, "decision": "rejected", "approver": "Rahul Kulkarni"}
    assert client.post("/approvals", json=body).json()["proposed_action"]["status"] == "rejected"


def test_the_record_holds_a_fingerprint_of_the_photo(make_client):
    client = make_client(ANSWER)
    photo = Path("data/images/crack_01.png").read_bytes()
    body = client.post("/inspect", data={"query": "q"}, files={"image": ("part.png", photo, "image/png")}).json()
    inputs = client.get(f"/transactions/{body['transaction_id']}").json()["inputs"]
    assert inputs["image_sha256"] == hashlib.sha256(photo).hexdigest()
    assert inputs["image_filename"] == "part.png"


def test_the_fingerprint_chain_detects_a_changed_record(make_client, db_path):
    client = make_client(ANSWER * 3)
    for _ in range(3):
        transaction_id = client.post("/inspect", data={"query": "q"}).json()["transaction_id"]
        client.post("/feedback", json={"transaction_id": transaction_id, "score": 1})
    assert client.get("/audit/verify").json() == {
        "transactions": {"intact": True, "rows_checked": 3, "broken_at_row": None},
        "events": {"intact": True, "rows_checked": 3, "broken_at_row": None},
    }

    # Someone with full database access removes the protection and edits the second record.
    conn = sqlite3.connect(db_path)
    conn.execute("DROP TRIGGER transactions_no_update")
    conn.execute("UPDATE transactions SET answer = 'changed' WHERE rowid = 2")
    conn.commit()
    conn.close()

    report = client.get("/audit/verify").json()
    assert report["transactions"] == {"intact": False, "rows_checked": 1, "broken_at_row": 2}
    assert report["events"]["intact"] is True


def test_a_slow_model_gets_the_ready_made_reply_and_is_not_tried_again():
    client = ScriptedClient([step("search_rules", "scratch limits", True), ModelTimeout("too slow")])
    result = run_turn(
        client, "m", retrieve, "Is this OK?", vision=scratch(15.0), choose_top_k=lambda state: (5, "best_known"), time_limit=30
    )

    assert (result.decision, result.reason, result.proposed_action) == ("ready_made_reply", "time_limit", None)
    assert "taking too long" in result.answer and "A scratch up to 10 mm long is acceptable." in result.answer
    assert "No decision has been made" in result.answer and "length_mm 15.0 mm" in result.answer
    assert result.rules[0]["section"] == "1.2"
    # The setting in use is kept, so feedback on this reply still counts in the learning.
    assert (result.top_k, result.top_k_choice) == (5, "best_known")
    assert [s["tool"] for s in result.trace] == ["search_rules", "ready_made_reply"]
    assert client.replies == []


def test_a_slow_planning_step_also_falls_back():
    client = ScriptedClient([ModelTimeout("too slow")])
    result = run_turn(client, "m", retrieve, "What is the scratch limit?", choose_top_k=lambda state: (3, "trying_another"), time_limit=30)
    assert (result.decision, result.top_k, result.top_k_choice) == ("ready_made_reply", 3, "trying_another")
    assert [s["tool"] for s in result.trace] == ["ready_made_reply"]

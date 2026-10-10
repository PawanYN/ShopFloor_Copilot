"""Print the model's raw reply for chosen answer cases, to see why a case fails.

    python scripts/show_raw_answers.py llama3.2 "scratch well under" "crack"
"""

import json
import sys
import tempfile
from pathlib import Path

from app import config
from app.knowledge.answer import answer_question, search_text
from app.knowledge.index import build_index
from app.knowledge.retrieval import search
from app.knowledge.store import ChromaPassageStore
from app.llm import OllamaClient


class RecordingClient(OllamaClient):
    def chat_json(self, model, system, user, schema):
        self.last = super().chat_json(model, system, user, schema)
        return self.last


model, wanted = sys.argv[1], sys.argv[2:]
cases = json.loads((Path(config.EVAL_DIR) / "answer_cases.json").read_text(encoding="utf-8"))
cases = [case for case in cases if any(text in case["name"] for text in wanted)]

with tempfile.TemporaryDirectory() as path:
    store = ChromaPassageStore(path, config.EMBEDDING_MODEL)
    build_index(store, config.EMBEDDING_MODEL)
    retrieved = [search(store, search_text(c["question"], c.get("vision")), 5, config.EMBEDDING_MODEL) for c in cases]

client = RecordingClient()
for case, hits in zip(cases, retrieved):
    answer = answer_question(client, model, case["question"], hits, case.get("vision"))
    print(f"\n=== {case['name']} (wanted {case['decisions']}) {client.last.seconds}s, retrieved {[hit.id for hit in hits]}")
    print("raw:", json.dumps(client.last.data))
    print("->", answer.decision, f"({answer.reason}):", answer.message)

# ShopFloor Copilot

AI-assisted visual inspection and SOP agent for a manufacturing shop floor, built as an FDE candidate assignment. The brief is in `business_docs/FDE_Candidate_Assignment.pdf`; read it before making design choices.

The assignment is time-boxed to 4–5 focused hours. Prefer the simplest version that satisfies each requirement, and note any shortcut in `README.md`.

## Hard constraints

- Open-source and local tooling only. No managed cloud AI APIs (OpenAI, AWS, GCP, Azure, Rekognition, Textract, Google Vision).
- No deep-learning training runs. Classical CV or a pretrained off-the-shelf model is the ceiling for vision.
- The RL loop is a hand-rolled epsilon-greedy contextual bandit or simple Q-learning, not a neural network.
- Any agent path ending in "escalate" or "flag for scrap" returns a proposed action. Nothing is executed or posted without the simulated human-approval step.
- Every `/inspect` call is written to the append-only audit log: timestamp, transaction ID, inputs, tools called, model/config used, final answer, latency.
- The decision trace must show which tools were called, in what order, and why.

## Stack

- API: FastAPI, Uvicorn, Pydantic
- Vision and OCR: OpenCV, Pillow, EasyOCR or pytesseract, optionally Ultralytics YOLOv8n
- Vector store: ChromaDB, FAISS, or an in-memory cosine index
- LLM: Ollama running a local open-source model

## Endpoints

- `POST /inspect` — text query, optional part image, optional `work_order_id`
- `POST /feedback` — transaction ID and a 0/1 score; updates the bandit directly
- `GET /transactions/{id}` — replays a past decision trace and its configuration

## RL loop

- State: detected defect category, or "no image supplied"
- Action: one axis only (OCR engine or RAG top-K)
- Reward: (feedback score × 10) − latency in seconds

## Out of scope

UI or mobile client, production auth, multi-tenancy, deployment infrastructure.

## Repository layout

- `docs/` — project documentation, including `DECISIONS.md` (Section G rationale)
- `business_docs/` — the assignment brief

## Git

- Default branch is `main`; remote is `origin` (github.com/PawanYN/ShopFloor_Copilot).
- Do not add Claude co-author or "Generated with Claude Code" lines to commits or pull requests.
- Commit or push only when asked.

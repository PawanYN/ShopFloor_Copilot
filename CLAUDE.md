# ShopFloor Copilot

AI-assisted visual inspection and SOP agent for a manufacturing shop floor, built as an FDE candidate assignment. The brief is in `business_docs/FDE_Candidate_Assignment.pdf`; read it before making design choices.

Prefer the simplest version that satisfies each requirement, and note any shortcut in `README.md`.

## Hard constraints

- Open-source and local tooling only. No managed cloud AI APIs (OpenAI, AWS, GCP, Azure, Rekognition, Textract, Google Vision).
- No deep-learning training runs. Classical CV or a pretrained off-the-shelf model is the ceiling for vision.
- The RL loop is a hand-rolled epsilon-greedy contextual bandit or simple Q-learning, not a neural network.
- Any agent path ending in "escalate" or "flag for scrap" returns a proposed action. Nothing is executed or posted without the simulated human-approval step.
- Every `/inspect` call is written to the append-only audit log: timestamp, transaction ID, inputs, tools called, model/config used, final answer, latency.
- The decision trace must show which tools were called, in what order, and why.

## Running

Everything runs in Docker (the API, Ollama, and any tooling). Do not install anything on the host machine: no pip installs, no Ollama or Tesseract installers, no winget. Run scripts and tests inside the containers.

## How we work

- `docs/ROADMAP.md` is the plan: the architecture, the phases, and the numbered open decisions.
- Do not fix a tool, library, model, parameter or approach on your own, even a small one (for example whether reranking is needed). Wherever "why this?" could be asked, present the options, trade-offs and a recommendation, and let the user decide.
- Reason about every choice as a real production decision. This is a demo, so assume whatever resources are needed (including a GPU) are provided; never justify or reject an option because of the local machine's CPU, memory or disk.
- Explain every decision in simple, everyday words from the start: say what the problem is, give the choices, and use a small example. Avoid jargon; where a technical term is needed, say what it means.
- Ask one decision at a time and wait for the answer before raising the next. Never present a batch of decisions in one message.
- Record every decision in `docs/DECISION_LOG.md` when it is made, using the roadmap's decision number. Section G in `docs/DECISIONS.md` is written from that log.
- Work on one phase at a time, in the roadmap's order. Discuss that phase's decisions before building it.
- Note any shop-floor risk that is noticed but not solved; it feeds Section G question 5.

## Stack

Decided during the build; the reasons are in `docs/DECISION_LOG.md`.

- API: FastAPI, Uvicorn, Pydantic
- Vision and OCR: classical OpenCV, Tesseract through pytesseract
- Knowledge: ChromaDB, `bge-m3` embeddings and `llama3.1` served by Ollama
- Agent: a plain-Python loop with structured output, no agent framework
- Storage: SQLite for audit records and learning scores, MongoDB for conversations

## Endpoints

- `POST /inspect` — text query, optional part image, optional `work_order_id`
- `POST /feedback` — transaction ID and a 0/1 score; updates the learning loop directly
- `GET /transactions/{id}` — replays a past decision trace and its configuration
- `POST /approvals` — a person approves or rejects a proposed action
- `GET /audit/verify` — checks the fingerprint chain of the audit records

## RL loop

- State: detected defect category, or "no image supplied"
- Action: one axis only (OCR engine or RAG top-K)
- Reward: (feedback score × 10) − latency in seconds

## Out of scope

UI or mobile client, production auth, multi-tenancy, deployment infrastructure.

## Repository layout

- `docs/` — `ROADMAP.md` (plan and open decisions), `DECISION_LOG.md` (decisions as made), `DECISIONS.md` (Section G rationale)
- `business_docs/` — the assignment brief

## Git

- Default branch is `main`; remote is `origin` (github.com/PawanYN/ShopFloor_Copilot).
- Do not add Claude co-author or "Generated with Claude Code" lines to commits or pull requests.
- Commit or push only when asked.

# ShopFloor Copilot

An AI-assisted visual inspection and SOP assistant for a manufacturing shop floor. A line worker sends a photo of a part and/or a question ("Is this within tolerance?", "Who do I escalate a crack to?"). The assistant checks the photo, searches the plant's SOPs, answers with the rule it used, and records every step it took.

Everything runs locally on open-source tooling. No managed cloud AI service is used.

- The reasoning behind the design is in [docs/DECISIONS.md](docs/DECISIONS.md) (the Section G rationale).
- Every design choice, with the options considered and the evidence, is in [docs/DECISION_LOG.md](docs/DECISION_LOG.md).
- The plan and architecture are in [docs/ROADMAP.md](docs/ROADMAP.md).

## Run it

You need Docker with Docker Compose. Nothing is installed on the host.

```bash
docker compose up --build
```

The first start downloads two models through Ollama, about 6 GB in total, so it takes a while. Later starts are quick. The service is ready when `curl http://localhost:8000/health` returns `{"status":"ok"}`.

With an NVIDIA GPU, add the GPU file:

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build
```

Four containers start:

| Container | What it does |
|---|---|
| `api` | the FastAPI service: agent, vision, search, learning loop, guardrails |
| `ollama` | serves the language model (`llama3.1`) and the embedding model (`bge-m3`) |
| `mongo` | stores conversations |
| `models` | downloads the two models on first start, then exits |

Speed depends on hardware. On the development laptop (a 4 GB graphics card, too small for the model) one answer takes 1 to 5 minutes. The time limit before the ready-made reply is therefore set to 600 seconds; set `LATENCY_CEILING_SECONDS=10` on a server with a suitable GPU.

## Try each endpoint

Sample part photos are in [data/images/](data/images/). Run these from the repository root. Interactive API pages are at http://localhost:8000/docs.

**Ask about a part, with a photo**

```bash
curl -X POST http://localhost:8000/inspect \
  -F "query=Is this part acceptable?" \
  -F "image=@data/images/surface_scratch_03.png"
```

The response holds the answer, the decision, the defect category, the ID read from the part, the rules cited, the configuration used, the step-by-step trace, the latency, a `transaction_id` and a `conversation_id`. For this photo the decision is `scrap`, returned as a `proposed_action` with status `pending_approval`.

**Ask a plain question**

```bash
curl -X POST http://localhost:8000/inspect -F "query=Who is the Quality Lead on the night shift?"
```

**Continue a conversation** (the photo sent earlier is remembered)

```bash
curl -X POST http://localhost:8000/inspect \
  -F "query=Who do I tell about this?" \
  -F "conversation_id=<conversation_id from an earlier response>"
```

**Give feedback** (1 is helpful, 0 is unhelpful; this updates the learning loop in the same call)

```bash
curl -X POST http://localhost:8000/feedback \
  -H "Content-Type: application/json" \
  -d '{"transaction_id": "<transaction_id>", "score": 1}'
```

**Replay a past decision**

```bash
curl http://localhost:8000/transactions/<transaction_id>
```

**Approve or reject a proposed action** (the simulated human-approval step)

```bash
curl -X POST http://localhost:8000/approvals \
  -H "Content-Type: application/json" \
  -d '{"transaction_id": "<transaction_id>", "decision": "approved", "approver": "Anita Deshmukh", "note": "Checked at the station"}'
```

**Check that the audit records were not changed**

```bash
curl http://localhost:8000/audit/verify
```

## How it works

```
Client: question + optional part photo + optional work-order ID
   |
   v
API layer
   |-- /inspect ----> Agent loop: the model picks the next tool, code runs it and records the step
   |                     |-- check_photo ------> defect type, measurement, ID read from the part
   |                     |-- search_rules -----> SOP passages -> answer, or limit check
   |                     |-- check_work_order -> mock lookup
   |                     |-- ask_worker -------> one question back to the worker
   |                     '-- send_to_person ---> proposed action, never executed
   |-- /feedback ---> Learning loop: reward = score x 10 - latency, updates the choice of top-K
   |-- /transactions/{id} -> replay of the stored trace and configuration
   '-- /approvals --> a person approves or rejects a proposed action
```

| Part | Folder | What it does |
|---|---|---|
| API | [app/api/](app/api/) | the endpoints and their request and response shapes |
| Agent | [app/agent/](app/agent/) | a plain-Python loop over five tools, at most 5 steps, with a trace written by code as each step happens |
| Vision and OCR | [app/vision/](app/vision/) | classical OpenCV: finds the part, measures it, classifies `no_defect`, `surface_scratch`, `crack` or `dimensional_deviation`; Tesseract reads the stamped `WO-12345` ID |
| Knowledge | [app/knowledge/](app/knowledge/) | five mock SOPs in [data/sops/](data/sops/), split by numbered section, embedded with `bge-m3`, stored in ChromaDB |
| Learning | [app/learning/](app/learning/) | an epsilon-greedy contextual bandit that picks the RAG top-K |
| Guardrails | [app/guardrails/](app/guardrails/) | the approval step and the photo fingerprint |
| Storage | [app/storage/](app/storage/) | SQLite for the audit records and learning scores, MongoDB for conversations |

Three design points are worth knowing before reading the code:

- **The model does not do the number check.** For a part check the model only copies the limits out of the SOP text and never sees the measurement. Ordinary code compares the number, sends a reading within the camera's 0.5 mm error of a limit to a person, and escalates when two SOPs disagree.
- **"Scrap" and "escalate" are only ever proposed.** They come back as a `proposed_action` and wait for `/approvals`. The service never posts anything onward.
- **The audit records cannot be quietly edited.** Database triggers reject every update and delete, feedback and approvals are stored as new rows, and each row carries a fingerprint covering the row before it, so `/audit/verify` detects a change made around the triggers.

## The learning loop

- **Method:** an epsilon-greedy contextual bandit ([app/learning/bandit.py](app/learning/bandit.py)).
- **State:** the defect category the camera found, or `no_image`.
- **Action:** the RAG top-K, chosen from 1, 3 and 5 passages.
- **Reward:** (feedback score × 10) − (latency in seconds), applied inside `POST /feedback`.
- **Choosing:** each value is tried once first. After that the best-scoring value is used, and about 1 time in 10 another value is tried. Each record says which of the two happened (`rag_top_k_choice`).
- **Updating:** each new reward moves the score a fixed step toward it, so recent results count more and the loop can follow SOP changes. Scores are stored in SQLite and survive a restart.

Why top-K and not the OCR engine: it affects every request including text-only questions, it changes the answer the worker rates, and it has a real trade-off, because more passages find the right rule more often but take longer to read.

### Observed behaviour

The log below comes from real answers, replayed. Every test case in [data/eval/answer_cases.json](data/eval/answer_cases.json) was answered once by the real system (`llama3.1`) with 1, 3 and 5 passages; a program marked each answer right or wrong against the known result, and the answer time was measured. Those 57 real results are saved in [data/eval/replay_outcomes.json](data/eval/replay_outcomes.json). They are then replayed for 600 rounds through the same bandit code the service uses, with a fixed seed.

What the real runs showed:

| Defect type (state) | Top 1 | Top 3 | Top 5 |
|---|---|---|---|
| `surface_scratch` (6 cases) | 5 right, 35 s | 6 right, 86 s | 6 right, 106 s |
| `dimensional_deviation` (4 cases) | 3 right, 34 s | 3 right, 115 s | 3 right, 137 s |
| `crack` (1 case) | 1 right, 63 s | 1 right, 105 s | 1 right, 105 s |
| `no_defect` (1 case) | 0 right, 32 s | 0 right, 86 s | 0 right, 198 s |
| `no_image` (7 cases) | 6 right, 16 s | 6 right, 16 s | 6 right, 17 s |

The seconds are from a development laptop whose graphics card is too small for the model, which is why they are so long. The reward gives 10 points for a right answer and takes away one per second, so at these times the wait swamps everything. For the replay the measured seconds are therefore divided by 20, so that a 100-second local answer counts as 5 seconds, about what a server with a suitable GPU would take. Which answers were right, and how much slower more passages are, stay exactly as measured. The service itself always uses the real seconds.

How often each top-K was used, in the first 30 and the last 30 questions of each defect type (seconds divided by 20):

| Defect type | First 30 questions | Last 30 questions | What happened |
|---|---|---|---|
| `surface_scratch` | top-1: 25, top-3: 2, top-5: 3 | top-1: 2, top-3: 27, top-5: 1 | shifted from 1 to 3 passages: with 1 passage one scratch case is answered wrongly, and 3 passages fixes it |
| `dimensional_deviation` | top-1: 2, top-3: 20, top-5: 8 | top-1: 26, top-3: 1, top-5: 3 | shifted from 3 to 1 passage: the answers are equally right at every value, so the fastest wins |
| `crack` | top-1: 26, top-3: 1, top-5: 3 | top-1: 29, top-3: 0, top-5: 1 | stayed on 1 passage: right at every value, and fastest |
| `no_defect` | top-1: 25, top-3: 1, top-5: 4 | top-1: 25, top-3: 1, top-5: 4 | stayed on 1 passage: wrong at every value, so only speed differs |
| `no_image` | top-1: 3, top-3: 21, top-5: 6 | top-1: 3, top-3: 26, top-5: 1 | settled on 3 passages; 3 and 5 score almost the same |

The scores behind the `surface_scratch` shift, from the replay log (k1, k3 and k5 are the scores for 1, 3 and 5 passages):

```
round 100   best top-1   k1=+7.1  k3=+6.1  k5=+4.0
round 200   best top-1   k1=+5.7  k3=+5.7  k5=+4.0
round 300   best top-3   k1=+5.2  k3=+5.9  k5=+4.1
round 400   best top-3   k1=+5.1  k3=+5.8  k5=+4.1
round 600   best top-3   k1=+4.6  k3=+5.4  k5=+4.3
```

The same replay with the raw local seconds shows why the adjustment was needed: every defect type with a photo stays on 1 passage from start to finish, because a 50-second difference outweighs the 10 points for a right answer. For `surface_scratch` the scores end at k1=−32.7, k3=−71.3, k5=−104.7, so the wrong-answer setting wins on speed alone.

To repeat it:

```bash
# slow: needs the models, about an hour on a laptop
docker compose run --rm -v "$(pwd)/data/eval:/srv/data/eval" api python -m app.learning.replay collect --model llama3.1
# fast: needs no model
docker compose run --rm --no-deps api python -m app.learning.replay run --rounds 600 --seed 7 --time-scale 20
docker compose run --rm --no-deps api python -m app.learning.replay run --rounds 600 --seed 7 --time-scale 1
```

Limits of this evidence: there are few cases per defect type (one each for `crack` and `no_defect`), the right-or-wrong mark comes from a program and not from a worker's opinion, and the quality difference between the values is small, one case out of nineteen.

On the live service, `POST /feedback` returns the update it made, for example `"learning": {"state": "surface_scratch", "rag_top_k": 1, "reward": -107.659, "score_after": -107.659}`.

## Evaluations

All of these run inside the containers and can be repeated.

**Vision** (`docker compose run --rm --no-deps api python -m app.vision.evaluate --per-category 25 --seed 11`, add `--hard` for the harder set)

| Image set | Category accuracy | Average measurement error | ID read correctly |
|---|---|---|---|
| Standard, 100 generated images | 100/100 | 0.34 mm | 96/100 |
| Hard, 100 generated images (more noise, lighting, rotation, blur) | 100/100 | 0.43 mm | 92/100 |

The classifier rules and the image generator were written together, so 100% shows the rules work on this generator, not on real parts.

**Retrieval** (`docker compose run --rm api python -m app.knowledge.evaluate --models all-minilm nomic-embed-text mxbai-embed-large bge-m3`, after pulling those models)

| Embedding model | Right section in top 1 | Top 3 | Top 5 |
|---|---|---|---|
| `all-minilm` | 15/21 | 20/21 | 20/21 |
| `nomic-embed-text` | 16/21 | 19/21 | 20/21 |
| `mxbai-embed-large` | 16/21 | 20/21 | 20/21 |
| `bge-m3` (selected) | 17/21 | 20/21 | 21/21 |

**Answer model** (`docker compose run --rm api python -m app.knowledge.evaluate_answers --models llama3.1 --judge none`)

| Model | Right decision on 19 cases |
|---|---|
| `llama3.2` (3B) | 15/19 |
| `mistral` (7B) | 16/19 |
| `llama3.1` (8B, selected) | 17/19 |

Only the final decision was scored in this run. A fourth model (`qwen2.5`) and a judge model for the written sentences were planned and not completed.

**Tokens per question**, counted by the model server for one plain question with `llama3.1`:

| What the model is given | Prompt tokens |
|---|---|
| Top 1 passage | 348 |
| Top 3 passages | 495 |
| Top 5 passages | 644 |
| All 30 passages (the whole SOP set, 1,632 words) | 2,954 |

Each count includes 271 tokens of instructions.

## Tests

```bash
docker compose run --rm --no-deps api python -m pytest -q
```

50 tests cover the vision rules, passage splitting, the number check, the agent loop, the learning loop, the approval step, the fingerprint chain and the endpoints. They use a stand-in for the language model, so they need no model download.

## Settings

Set these as environment variables before `docker compose up`.

| Variable | Default | Meaning |
|---|---|---|
| `ANSWER_MODEL` | `llama3.1` | the Ollama model that plans steps and writes answers |
| `EMBEDDING_MODEL` | `bge-m3` | the Ollama model used for search |
| `LATENCY_CEILING_SECONDS` | `600` | whole-request time limit before the ready-made reply; 10 is the value meant for a plant |

Other settings (top-K choices, explore rate, learning step, agent step limit, approval due time) are in [app/config.py](app/config.py).

## Shortcuts and known limits

- **Mock data.** The part photos are generated by a script and the five SOPs are written for this exercise.
- **Size limits are read unreliably.** The size rule has four ranges with directions, and no tested model copies it out reliably. In the answer test `llama3.1` accepted one part that should have been scrapped.
- **The camera is too coarse for the size tolerance.** Its error is about 0.5 mm against a 1.0 mm tolerance, so most size deviations are sent to a person instead of being decided.
- **The model may skip a photo.** The brief asks for the model to choose its tools, so it can answer from the SOPs without looking at a photo that was sent.
- **A misread ID can look valid.** On the hard image set, 3 of 100 IDs were read with one wrong digit and still matched the ID format.
- **The first answer for each defect type uses one passage**, because the learning loop tries each value once at the start.
- **The model sometimes raises an unneeded "send to a person"** on a plain question it answered correctly.
- **SQLite is used for the audit records.** PostgreSQL is the intended next step for more than one plant; the storage code sits behind one small interface for that reason.
- **The fingerprint chain detects tampering but does not prevent it**, and it would not catch someone who rewrites the whole chain.
- **No authentication.** Anyone who can reach the service can call `/approvals`. The brief places production auth out of scope.
- **The work-order lookup is a mock** with six fixed work orders.

# ShopFloor Copilot — Roadmap and Architecture

## Status

The build is complete. This document is kept as the original plan. Where the build went differently, [DECISION_LOG.md](DECISION_LOG.md) is the record of what was decided and why. The main changes from this plan:

- The agent has five tools, not four: "ask the worker" was added, and conversations are remembered and stored in MongoDB (decisions 4.5 and 4.10).
- Two endpoints were added to the three the brief requires: `/approvals` for the human-approval step and `/audit/verify` for the audit check (decisions 6.5 and 6.2).
- For a part check, the model only copies the limits from the SOP text and code does the comparison (decision 3.7).

## Purpose

The assignment weights the written decision rationale (Section G) equally with the code. Instead of writing that rationale at the end, each decision is made deliberately during the build and recorded at that moment.

So this roadmap does two things:

- It fixes only what the brief or the project has already fixed.
- Everything else is listed as an **open decision**: a question, the options, and nothing chosen. Each one is discussed when its phase is reached, and the outcome goes into a decision log that later becomes the Section G answers in [DECISIONS.md](DECISIONS.md).

Work proceeds one area at a time, in this order: foundation, vision, knowledge (policies and protocols), answering from knowledge, agent, feedback, guardrails, write-up.

## What is fixed and what is open

**Fixed by the brief**

- Three endpoints: `POST /inspect`, `POST /feedback`, `GET /transactions/{id}`, with the inputs and outputs the brief lists.
- Open-source, local tooling only. No managed cloud AI services. No deep-learning training runs.
- A Python API, a defect classifier with 3–4 categories, and reading the ID printed on the part.
- 3–5 mock knowledge documents, retrieved through a vector store.
- A local open-source language model, run through Ollama.
- An agent loop that chooses between: answer from knowledge, call vision/OCR, check work-order status (mock), escalate to a human. The trace must show which step, in what order, and why.
- One learning loop. State is the defect category (or "no image"). It tunes one setting only. Reward is (feedback × 10) − latency in seconds.
- An audit record for every `/inspect` call, a human-approval step before escalate or scrap, and a latency ceiling with a fallback.

**Fixed by project choice**

- Everything runs in Docker. Nothing is installed on the host machine.

**Open**

Everything else, including choices where the brief only gives a suggestion or a short list (API framework, OCR engine, vector store, model, learning algorithm, and so on).

## Architecture

This is the logical shape only. No box implies a specific tool.

```
Client: question + optional part photo + optional work-order ID
   |
   v
API layer
   |-- /inspect ------------> Agent loop (decides each step, records why)
   |                             |-- tool: Vision + OCR ------> defect type, ID read from the part
   |                             |-- tool: Knowledge search --> SOP text -> grounded answer
   |                             |-- tool: Work-order status -> mock lookup
   |                             |-- tool: Escalate ----------> proposed action, never executed
   |                             '-- asks the Learning loop which setting to use
   |
   |-- /feedback -----------> Learning loop (reward = score x 10 - latency) -> updates its choice
   |
   '-- /transactions/{id} --> Replay (reads the stored decision trace and setting)

Always on, not chosen by the agent:
   Audit log | Human-approval gate | Latency ceiling + fallback

Shared underneath:
   Local language model | SOP index | Transaction + audit store | Learning state | Pending approvals
```

**How one `/inspect` request moves through it**

1. The API accepts the request, creates a transaction ID and starts a timer.
2. The agent loop decides the first step.
3. If a photo is present and the agent calls vision, it gets back a defect type and the ID read from the part.
4. The defect type (or "no image") is the state. The learning loop picks one setting for that state.
5. Knowledge search finds the relevant SOP text, and the language model writes an answer grounded in it.
6. If needed, the agent checks the work-order status.
7. If the result is "escalate" or "scrap", it is returned as a proposed action waiting for approval.
8. If the model is slower than the ceiling, the fallback answers instead.
9. The audit record is written, and the response returns the answer, defect type, ID text, setting used, trace, latency and transaction ID.

`/feedback` looks up the transaction, computes the reward, and updates the learning loop. `/transactions/{id}` reads the stored record back.

## How each phase is worked

1. **Discuss** the phase's open decisions: options, trade-offs, a recommendation. Then decide.
2. **Record** each decision in the decision log: the question, options considered, the choice, why, and what would change it.
3. **Build** the simplest version that meets the brief.
4. **Check** by running the phase's "done when" check inside Docker.
5. **Commit.**

Alongside this, keep a running list of shop-floor risks that are noticed but not solved. That list feeds Section G question 5.

**Decisions to take first**, because each one shapes more than one phase:

- **5.2** which setting the learning loop tunes. It decides whether vision needs two OCR engines or retrieval needs several top-K values.
- **1.4** whether vision returns only a category or also measurements. It decides what the SOP documents must contain and how "within tolerance" is answered.
- **0.2** CPU or GPU, and the container layout. It sets how slow the model is, which drives the reward and the fallback.
- **0.4** where transactions and audit records are stored. Every phase writes to it.
- **0.8** the time budget per phase.

## Phases

Decision numbers are phase number, then item number.

### Phase 0 — Foundation

**Goal:** a service that starts in Docker with the three endpoints responding, so every later area plugs into something that runs.

**Builds:** the container setup, the API shell with placeholder responses, transaction IDs, and a first version of the audit record.

**Open decisions**

- 0.1 API framework. The brief recommends one but leaves it open.
- 0.2 Container layout: one container or several, how model files persist between runs, CPU only or GPU.
- 0.3 Request format for `/inspect`: multipart form, base64 in JSON, or both.
- 0.4 Where transactions and audit records are stored: flat file, embedded database, or other.
- 0.5 How settings such as the latency ceiling are supplied: file or environment variables.
- 0.6 Code layout: how the six parts map to modules.
- 0.7 Testing depth: automated tests, scripted checks, or curl examples only.
- 0.8 Time budget per phase, given the brief's 4–5 hour guidance.

**Done when:** one command starts the service; the three endpoints respond; a transaction ID returned by `/inspect` can be read back from `/transactions/{id}`.

### Phase 1 — Vision

**Goal:** from a part photo, get a defect category and the ID printed on the part, with results that are real and repeatable.

**Builds:** the mock part images, the defect classifier, the ID reader, and a small evaluation run.

**Open decisions**

- 1.1 Defect categories: which 3–4, and whether there is an "uncertain" outcome.
- 1.2 Mock images: generated by a script or taken from an open dataset; how many; how much variation (lighting, noise, rotation).
- 1.3 Classifier approach: classical image processing, a pretrained model, or both.
- 1.4 What vision returns: category only, or also measurements (scratch length, size error) and a confidence value.
- 1.5 How dimensional deviation is judged: against what reference size, and where that reference comes from.
- 1.6 OCR engine: which one, and one or two (two are needed only if 5.2 picks OCR engine).
- 1.7 Image clean-up before OCR: none, crop to the ID area, thresholding, straightening.
- 1.8 ID format and validation: what pattern, and what happens when the text read does not match it.
- 1.9 One tool or two: whether the agent can call "classify" and "read ID" separately.
- 1.10 How accuracy is measured and reported.

**Done when:** the image set can be regenerated; an evaluation run prints accuracy per category and the ID match rate; a rerun gives the same numbers.

**Feeds:** Section G question 3.

### Phase 2 — Knowledge (policies and protocols)

**Goal:** write the plant's rules, then make the right passage findable for a given question.

**Builds:** the mock documents (tolerance specs, rework-vs-scrap rules, escalation contacts and rules), the indexing step, and retrieval.

**Open decisions**

- 2.1 Document set: how many, how long, what file format, how realistic.
- 2.2 Content shape: prose only or tables too; rules per defect category, per part, or both.
- 2.3 Hard cases on purpose: overlapping or conflicting rules, version and effective dates. Include or not.
- 2.4 Link to vision: whether tolerance limits use units that vision can actually measure (depends on 1.4).
- 2.5 Why vector search rather than reading all documents in one prompt. The brief requires a vector store, but the reasoning is ours to give.
- 2.6 Which vector store.
- 2.7 Chunking: by section, paragraph or fixed size; overlap; keeping tables whole.
- 2.8 Labels on each chunk (document, section, defect category), and whether retrieval filters by them.
- 2.9 Embedding model: which one, and where it runs.
- 2.10 Extras, each "needed or not": keyword plus vector search, reranking, query rewriting.
- 2.11 When the index is built: at image build, at startup, or by a separate command.
- 2.12 How retrieval quality is checked.

**Done when:** for a small set of test questions, the expected passage appears in the retrieved results.

**Feeds:** Section G question 1.

### Phase 3 — Answering from knowledge

**Goal:** turn retrieved rule text, plus what vision found, into an answer a line worker can act on.

**Builds:** the connection to the local model, the prompt, and the answer format.

**Open decisions**

- 3.1 Which local model: size against speed against quality on the hardware from 0.2.
- 3.2 A second model: needed or not. The brief calls it a bonus; it also relates to the fallback in 6.8.
- 3.3 Prompt layout: how retrieved text, the vision result and work-order details are combined.
- 3.4 Answer shape: free text, fixed fields, or both.
- 3.5 Source references in the answer (document and section): needed or not.
- 3.6 When no relevant text is found: refuse, escalate, or answer with a warning.
- 3.7 Who decides "within tolerance": the model reading the spec, or code comparing numbers.
- 3.8 Repeatability: how much randomness the model is allowed, given that decisions are replayed for audit.
- 3.9 How answer quality is checked.

**Done when:** for the test questions, answers agree with the documents; a question with no supporting text is handled by the rule agreed in 3.6; and the tokens per question are measured for vector search and for reading the whole document set, giving a real cost table for Section G question 1.

**Feeds:** Section G questions 1 and 4.

### Phase 4 — Agent

**Goal:** for each query, the model chooses the path, and the trace explains it.

**Builds:** the agent loop, the tool definitions, the mock work-order tool, the escalation path, and the decision trace.

**Open decisions**

- 4.1 A hand-written loop or an agent framework.
- 4.2 How the model states its choice: built-in tool calling, structured output, or parsed text.
- 4.3 A malformed or stuck step: retry, take a default path, or escalate.
- 4.4 Limits: maximum steps, time budget, stop conditions.
- 4.5 Tool list and contracts, and whether "answer from knowledge" is a tool or the final step.
- 4.6 The mock work-order tool: which fields, which sample orders, what an unknown ID returns.
- 4.7 What is deliberately not agentic. Candidates: running vision whenever a photo is present, audit logging, the approval gate, the learning loop's choice, the latency fallback.
- 4.8 Escalation triggers: the model's judgement, fixed rules taken from the SOPs, or both.
- 4.9 Trace format: the fields per step, and where the "why" comes from (recorded by code as it happens, or written by the model).

**Done when:** four example queries each take a different path (answer from knowledge, photo to vision, work-order lookup, escalation), and each trace shows the steps, their order and the reasons.

**Feeds:** Section G question 2.

### Phase 5 — Feedback

**Goal:** the system visibly changes which setting it picks as feedback arrives.

**Builds:** the learning loop, the `/feedback` update, and a run that produces the log or plot for the README.

**Open decisions**

- 5.1 Algorithm: epsilon-greedy contextual bandit or simple Q-learning.
- 5.2 Which setting it tunes: OCR engine or RAG top-K. The brief's response description also mentions "which LLM". This choice must be justified in the rationale.
- 5.3 The options for that setting: how many and which values.
- 5.4 Exploration: the rate, fixed or decreasing, and the starting estimates.
- 5.5 Update rule: running average or fixed step size.
- 5.6 Where in the request the choice is made. The state is known only after vision has run.
- 5.7 Which latency counts in the reward: the whole request or only the part the setting affects. With a slow model, latency can outweigh the feedback score.
- 5.8 Feedback rules: once per transaction or not, late feedback, unknown transaction ID.
- 5.9 Where the learning state is stored, and whether it survives a restart.
- 5.10 How the shift is shown: simulated users, a log or a plot, a fixed random seed.
- 5.11 Whether "explored" or "used the best known" is recorded in the trace.

**Done when:** a repeatable run shows the chosen setting per defect category shifting as feedback accumulates, and a call to `/feedback` changes the stored estimates.

**Feeds:** the action-axis justification, and Section G question 4.

### Phase 6 — Guardrails

**Goal:** every decision is auditable, nothing irreversible happens without a person, and a slow model does not block the line.

**Builds:** the complete audit record, the approval step, and the latency ceiling with its fallback.

**Open decisions**

- 6.1 What "inputs" means in the audit record for a photo: the image itself, a fingerprint of it, or a file path.
- 6.2 How "append-only" is enforced or shown, and whether tamper evidence is needed.
- 6.3 Whether feedback and approval events are logged too.
- 6.4 Which outcomes need approval: escalate and scrap per the brief; rework as well or not.
- 6.5 How approval is simulated: an extra endpoint, a status field, or a command.
- 6.6 The states a proposed action can be in, and whether it expires.
- 6.7 The latency ceiling: its value, what it is measured on, and how the slow call is stopped.
- 6.8 The fallback: a smaller model, a cached answer, or a templated response.
- 6.9 Whether fallback responses count in the learning loop.
- 6.10 Response caching: needed or not.

**Done when:** every `/inspect` call has a complete record; an escalate or scrap result comes back as a pending proposed action and changes only after approval; a forced slow response triggers the fallback and is marked as such in the response and the record.

**Feeds:** Section G questions 4 and 5.

### Phase 7 — Write-up and submission

**Goal:** a reviewer can clone, run and test everything, and read a rationale that reflects decisions actually made.

**Builds:** the README (setup, learning strategy and observed behaviour, a curl example per endpoint, shortcuts taken), the final Section G answers written from the decision log, and the dependency file.

**Open decisions**

- 7.1 README structure, and whether the learning results sit in the README or a separate file.
- 7.2 Bonus items, each "needed or not": a single-page test harness, a second model.
- 7.3 Which shortcuts to declare.

**Done when:** from a fresh clone, the documented commands start the service and every curl example works; each of the five Section G answers can be traced to entries in the decision log.

## How the decisions feed Section G

| Section G question | Decisions that feed it |
|---|---|
| 1. Vector RAG vs. long-context read | 2.1, 2.5, 2.7, 2.10 |
| 2. Agent loop vs. fixed pipeline; what is not agentic | 4.1, 4.7, 4.8 |
| 3. Classical CV, pretrained model, or both | 1.2, 1.3, 1.10 |
| 4. First cost lever when scaling to ten plants | 3.1, 3.2, 6.8, 6.10, plus measured latencies |
| 5. A shop-floor governance risk not yet addressed | 6.1–6.6, plus the running risk list |
| Action-axis justification (Section E) | 5.2, 5.3, 5.7 |

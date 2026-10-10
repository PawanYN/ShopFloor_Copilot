# ShopFloor Copilot — Decision Log

One entry per decision, recorded when it is made. Decision numbers match the open decisions in [ROADMAP.md](ROADMAP.md). The Section G answers in [DECISIONS.md](DECISIONS.md) are written from this log.

## Entry format

```
### <number> — <the question>

- Date:
- Options considered:
- Choice:
- Why:
- What would change it:
- Feeds Section G question:
```

## Decisions made before the roadmap

### Run everything in Docker

- Date: 2026-10-09
- Options considered: install the tooling on the host machine; run everything in containers.
- Choice: everything runs in Docker. Nothing is installed on the host machine.
- Why: to be recorded.
- What would change it: to be recorded.
- Feeds Section G question: none directly. It constrains decision 0.2.

## Roadmap decisions

### 0.1, 0.3, 0.5, 0.7 — Foundation defaults

Accepted as proposed defaults on 2026-10-09, without in-depth discussion.

| # | Choice | Why | Alternative considered |
|---|---|---|---|
| 0.1 | FastAPI as the API framework | recommended by the brief; checks inputs and gives a built-in test page | Flask |
| 0.3 | The photo is sent to `/inspect` as a multipart form | a curl example stays short (`-F image=@part.png`) | base64 inside JSON |
| 0.5 | Settings come from environment variables with defaults, set in the compose file | changing a setting needs no code change or rebuild | a settings file in the repo |
| 0.7 | A few automated tests where there is a clear right answer, plus curl examples | covers the learning update, the audit table rejecting edits, and vision accuracy at low cost | curl examples only |
| — | Python 3.12 inside the container | some vision and vector libraries are slower to support the newest release | Python 3.13 |

### 0.2 — Container layout and hardware

- Date: 2026-10-09
- Options considered: one container holding the API and the model runtime, or two separate containers; CPU only, GPU only, or CPU by default with an optional GPU setting.
- Choice: two containers (API, model runtime), model files in a volume so they download once, CPU by default with an optional GPU setting for local runs.
- Why: the official model-runtime image is used unchanged; a code change rebuilds only the small API container while the model stays loaded; the API stays alive to return the fallback if the model is slow or down; the model runtime can later move to a bigger shared machine without touching the API. CPU by default runs on any reviewer's machine.
- What would change it: a requirement to ship a single self-contained image, or a guarantee that every target machine has a GPU.
- Update 2026-10-10: choices are now reasoned as production decisions, with a GPU assumed to be available. The two-container layout stands. Development and evaluation runs use the GPU setting; "CPU by default" remains only so the project starts on a machine without a GPU.
- Feeds Section G question: 4.

### 0.4 — Where transactions and audit records are stored

- Date: 2026-10-09
- Options considered: a text file with one record per line; an embedded SQL database (SQLite); a text file plus a database; a server SQL database (PostgreSQL) in its own container.
- Choice: a structured SQL database. Embedded (SQLite) during development, moving to PostgreSQL at the final stage. Tables are kept plain so the move is a configuration change.
- Why: the embedded database is a single file, so a fresh one can be created for each evaluation run and the old ones kept as history, which makes it easy to compare runs and see how the system improves. It also needs no extra container or setup while building. SQL over a text file because the data is related (feedback and approvals point to a transaction), the questions asked of it are queries (reward per defect type per setting, pending approvals), the database rejects bad data, and each write is all-or-nothing.
- What would change it: several API instances writing at once, or more than one plant, which is when the server database becomes necessary rather than optional.
- Feeds Section G question: 4, and 5 through the audit trail.

### 0.6 — Code layout

- Date: 2026-10-09
- Options considered: one folder per part of the system; one folder per endpoint; one folder per technical role (routes, services, models); a flat set of files; core logic plus adapters behind interfaces.
- Choice: one folder per part (`api`, `agent`, `vision`, `knowledge`, `learning`, `guardrails`, `storage`), with a small interface at two known swap points: storage and the model client. Calls go downward only: `api` calls `agent`; `agent` calls `vision`, `knowledge`, `learning` and `guardrails`; all may call `storage`; nothing calls back up.
- Why: the code has the same shape as the architecture diagram and the brief's sections A–F, so a reviewer finds each part in one place, each phase fills one folder, and each part can be tested alone. Per-endpoint was rejected because `/inspect` is about 90% of the system; per-role scatters vision code across folders; flat is hard to review; full core-plus-adapters is too much code for a 10-hour build.
- What would change it: many independent endpoints, or many more swappable outside systems, which would justify per-endpoint folders or interfaces everywhere.
- Feeds Section G question: none directly.

### 0.8 — Time budget per phase

- Date: 2026-10-09
- Options considered: the brief's 4–5 focused hours; a longer budget.
- Choice: 10 hours in total. Build: foundation 0:30, vision 1:00, knowledge 0:45, answering 0:45, agent 1:00, feedback 1:00, guardrails 0:45, write-up and Section G 1:15. Discussions 2:00, buffer 1:00. The roughly 20 decisions that feed Section G are discussed in depth; the rest get a one-line default that can be accepted or challenged.
- Why: to be recorded.
- What would change it: to be recorded.
- Feeds Section G question: none directly.

### 1.1, 1.2, 1.3, 1.6 — Vision choices taken from the brief

Decided on 2026-10-10 as "start with what the brief says" (Section B).

| # | Choice | Why | Alternative considered |
|---|---|---|---|
| 1.1 | The brief's four categories: `no_defect`, `surface_scratch`, `crack`, `dimensional_deviation` | they are the brief's own example and cover three different kinds of evidence (a line, a jagged line, a size) | other category sets; a fifth "uncertain" category |
| 1.2 | A handful of images generated by a script (3 per category committed), with a fixed seed | the brief asks for "a handful"; a generator gives a known true category, measurement and ID for each image. Larger sets are generated on demand for evaluation only | an open dataset of real defects |
| 1.3 | Classical OpenCV techniques only (thresholding, contour analysis) | the brief says the point is "demonstrating the underlying CV/OCR technique", and asks for a lightweight classifier; rules also give measurements and an explanation directly | a pretrained zero-shot model; both together |
| 1.6 | pytesseract (Tesseract) as the single OCR engine | one of the two engines the brief names; a small install and fast on CPU | EasyOCR |

- What would change 1.3: real shop-floor photos where rule accuracy drops under varied lighting and surface texture, plus a few hundred labelled examples per category. That is the point to fine-tune a custom model.
- Known weakness of 1.2: the classifier is tested on defects the project drew itself, so the accuracy figures show the rules work on this generator, not on real parts.
- Feeds Section G question: 3.

### 1.4 — What vision returns

- Date: 2026-10-09
- Options considered: defect category only; category plus one measurement and a confidence value.
- Choice: category, one measurement per defect, and a confidence value.
- Why: a measurement lets the system compare a number against the SOP limit and give a real yes or no to "Is this within tolerance?", instead of only quoting the rule. A confidence value allows an "uncertain, so escalate" path.
- What would change it: real shop-floor photos with no known scale. The pixel-to-millimetre conversion holds only because the mock images are generated with a known scale.
- Feeds Section G question: 3. It also constrains decisions 2.4 and 3.7.

### 1.5, 1.7, 1.8, 1.9, 1.10 — Vision defaults (provisional)

Proposed defaults used to build Phase 1 on 2026-10-10. Not individually confirmed; open to challenge.

| # | Default in use | Alternative |
|---|---|---|
| 1.5 | Dimensional deviation is the measured part outline compared with a nominal size held in a small spec in code. The acceptance tolerance is no longer in code: see 2.4 and 2.4a | nominal size in the SOP text only |
| 1.7 | Minimal clean-up before OCR: crop the ID area and threshold; add steps only if the match rate is poor | crop and straighten from the start |
| 1.8 | One stamped ID in the form `WO-12345`; text that does not match is returned flagged as unreadable, never guessed | accept any text read |
| 1.9 | One image tool returning category, measurement, confidence and ID together | separate "classify" and "read ID" tools |
| 1.10 | One evaluation command printing accuracy per category, a confusion table, measurement error and ID match rate, on a standard and a harder set | the standard set only |

### Phase 1 results (2026-10-10)

Measured inside the container on generated sets of 100 images (25 per category, seed 11). A rerun gives the same numbers.

| Set | Category accuracy | Average measurement error | ID exact match |
|---|---|---|---|
| Standard | 100/100 | 0.34 mm | 96/100 |
| Hard (stronger noise, lighting, rotation, blur) | 100/100 | 0.43 mm | 92/100 |
| Committed handful (12 images, seed 7) | 12/12 | 0.40 mm | 12/12 |

Figures are after the size-measurement change of decision 2.4a. Before it they were 0.57 mm / 97, 0.60 mm / 93 and 0.54 mm / 12.

- 1.7 changed after measuring: with crop and threshold only, the ID match rate was 78%. Enlarging the ID area twofold raised it to 90%; restricting Tesseract to the ID's characters (`WO-0123456789`) raised it to 97%.
- The ID must match the pattern as a whole. A misread with an extra digit (`WO-153382`) is returned as unreadable, not trimmed to a valid-looking ID.
- The hard set does not break the classifier, so these sets do not show where the rules fail. 100% reflects that the rules and the generator were written together (see the weakness under 1.2).

### 2.1 — The document set

- Date: 2026-10-10
- Options considered: three documents (one per topic the brief names); four or five; ten to fifteen.
- Choice: five short markdown documents of about a page each, with several numbered sections per document (about 25 passages in total): tolerance specs, rework-vs-scrap rules, escalation contacts and rules, an inspection procedure, and a work-order handling note.
- Why: five stays inside the brief's "3–5 short documents" and is quick to write, review and keep consistent with what vision measures. The two extra documents give the search text that is not the answer, so the retrieval test is more honest. Ten to fifteen would make retrieval and the top-K setting more meaningful, but goes beyond the brief and adds mock content that has to be read and stood behind.
- What would change it: top-K values giving results too similar to show a shift in the feedback phase. Adding documents is cheap, because a new document is another file in the folder and the index rebuilds from whatever is there.
- Feeds Section G question: 1.

### 2.2 — The form the SOP rules take

- Date: 2026-10-10
- Options considered: sentences only; sentences plus tables.
- Choice: sentences plus two tables, one for tolerance limits (defect type, limit, action) and one for escalation contacts.
- Why: real plant SOPs put limits and contacts in tables, so a system tested only on sentences would fail on real documents. Tables are harder for a model to read correctly, which makes this the more honest test.
- What would change it: the evaluation showing the model misreads the tables, which would call for converting tables to sentences at indexing time.
- Feeds Section G question: 1.

### 2.3 — Difficult cases put into the documents on purpose

- Date: 2026-10-10
- Options considered: tidy documents only; a version and effective date on each document; one deliberate conflict between two documents.
- Choice: every document carries a header with its number, revision and effective date, and the set includes one deliberate conflict between two documents. The rule for a conflict is: escalate to a human and show both passages.
- Why: the header lets each answer cite the revision it used, which an auditor asks for. Real plants have conflicting rules after partial revisions, and a system that confidently picks one of two conflicting rules is a shop-floor danger, so the conflict tests whether the system notices and escalates.
- What would change it: to be recorded.
- Feeds Section G question: 5.

### 2.4 — Where a tolerance limit lives

- Date: 2026-10-10
- Options considered: the limit in both the vision code and the SOP, kept equal by hand; vision only measures and the SOP holds every limit; one structured limits table that both read.
- Choice: vision only measures; the SOP decides. Vision reports a measurement (for example "width is 1.4 mm off nominal") and never judges it against an acceptance limit. Every limit is stated once, in the SOP, in millimetres to match what vision measures.
- Why: with the number in two places, a revised SOP and unchanged code would disagree, and the system would accept a part the SOP rejects. In a plant, tolerance limits are controlled values owned by quality engineering; with one source of truth, a limit is changed by revising a document, with no code change. A shared limits table is more robust still, but more work.
- What would change it: many part types with many limits, where a structured limits table read by both becomes worth building.
- Follow-up: done in decision 2.4a. The vision code no longer holds an acceptance limit.
- Feeds Section G question: 2 and 5.

### 2.4a — When vision labels a part "dimensional deviation"

- Date: 2026-10-10
- Options considered: label it whenever the size difference is larger than the camera's own measuring error; never label size in vision, and set the category after the SOP limit is looked up.
- Choice: vision labels `dimensional_deviation` when the part is off nominal by more than the camera's measuring error. The label is an observation ("the size is measurably off"); whether the amount is acceptable is decided from the SOP.
- Threshold: 0.5 mm, taken from measurement. On correctly sized generated parts, the size was read at most 0.50 mm off on both the standard and the hard set. A one-pixel correction in the size measurement was removed after it was found to add a constant error of about 0.22 mm.
- Why: the learning loop picks its setting from the defect label before the SOP is searched, so the label must exist early; with no size label, a part 3 mm too wide would be recorded as "no defect" next to a "reject" answer, which reads as an error in an audit; and knowing it is a size problem lets the search target size rules. The threshold is a property of the camera, not a quality rule.
- What would change it: a system where the label is not needed before the SOP lookup.
- Feeds Section G question: 2.

### 2.5 — Why vector search rather than reading all documents in one prompt

- Date: 2026-10-10
- Options considered: vector search that passes only the relevant passages to the model; reading the whole document set on every question.
- Choice: vector search, as the brief requires. Position for the rationale: it is right here because the SOP set keeps growing and answers must cite their source, but for a set fixed at 20 pages, reading everything would be the better design.
- Why: in production the cost of a question is the number of tokens the model must process, and that sets how many questions one GPU can serve. Vector search sends a few hundred tokens per question; reading a 20-page set sends about 14,000, roughly 30 times more compute per question, and the gap widens as the set grows. Each answer can also name the exact passage it used, which supports the audit trail, and a changed document is re-indexed alone. Reading everything has no search step, so nothing can be missed, and it is simpler.
- Measured (2026-10-10, prompt tokens counted by the model server for one plain question with `llama3.1`, each including 271 tokens of instructions): top 1 passage 348; top 3 passages 495; top 5 passages 644; all 30 passages, the whole set of 1,632 words, 2,954. Reading the whole set costs six times the top-3 prompt. At the same rate a 20-page set of about 10,000 words is roughly 16,000 tokens, over 30 times the top-3 prompt, which matches the earlier estimate.
- What would change it: a fixed, small document set (about 20 pages), where the whole set fits in the prompt and can be processed once and reused.
- Feeds Section G question: 1.

### 2.6 — Which vector store

- Date: 2026-10-10
- Options considered: a basic in-memory cosine index; FAISS; ChromaDB (the three the brief names).
- Choice: ChromaDB.
- Why: a real plant has a growing SOP set, revisions that replace old rules, and later several plants with different documents. ChromaDB keeps the index on disk, stores labels with each passage, filters by them (plant, document, version), and can replace or delete one document's passages when an SOP is revised. In-memory search is rebuilt on every restart, has no filtering, and each running copy of the service holds its own data. FAISS is built for speed over millions of vectors, a problem this system does not have, and leaves labels, filtering, updates and persistence to be built around it.
- What would change it: consolidating on PostgreSQL in production. Its vector extension (pgvector) could hold the passages next to the audit data, giving one database to run and back up. It is not on the brief's list, so it is named as a next step and not built.
- Feeds Section G question: 1 and 4.

### 2.7 — How documents are split into passages

- Date: 2026-10-10
- Status: provisional; may change after the retrieval evaluation (2.12).
- Options considered: by section heading; fixed size with overlap; by meaning, using a model to group sentences.
- Choice: by section heading, with a fallback to fixed size for any section that is too long.
- Why: plant SOPs are controlled documents with numbered clauses, so the structure is reliable, and the clause number is how supervisors and auditors already refer to a rule. One rule per passage keeps tables whole and lets every answer cite a real clause. Fixed size can cut a rule or table in half and gives a passage no natural name; splitting by meaning adds an indexing step and its cuts are hard to explain in an audit.
- What would change it: the retrieval evaluation showing misses caused by passage boundaries, or source documents without reliable headings (scans, free-form notes).
- Feeds Section G question: 1.

### 2.8 — Labels attached to each passage

- Date: 2026-10-10
- Options considered: labels used only for citing the source; labels also used to filter the search by defect type.
- Choice: each passage stores its document number, revision, effective date, section number and plant. The search filters by plant only. It does not filter by defect type.
- Why: the labels let every answer say exactly where it came from. A plant filter is a hard requirement in production, because a worker must never be given another plant's rule. A defect-type filter is risky: the most important rules, such as who to escalate to, apply to every defect and would be filtered out if a tag were wrong or missing.
- What would change it: a document set large enough that general search returns too many unrelated passages, where a defect-type filter with an explicit "applies to all" tag becomes worth the risk.
- Feeds Section G question: 1 and 5.

### 2.9 — Embedding model, and where it runs

- Date: 2026-10-10
- Status: decided on 2026-10-10 by evaluation. Choice: `bge-m3`, served by Ollama. The embedding model stays a setting, so it can be swapped and re-evaluated on the same retrieval test (2.12).
- Where it runs: served by Ollama next to the language model (confirmed by selecting an Ollama-served model). One runtime to deploy, monitor and scale, and the same model is used for indexing and for questions. The alternative is a library inside the API service, which removes a network call but makes the API carry model weights and scale as two things.
- Candidates (sizes and limits approximate, to be confirmed when pulled):

| Model | Size | Passage length accepted | Languages | Known for |
|---|---|---|---|---|
| `all-minilm` | about 23M parameters | about 256 tokens | English | speed; weakest quality |
| `nomic-embed-text` | about 137M | about 8,000 tokens | mainly English | a good general default |
| `mxbai-embed-large` | about 335M | about 512 tokens | English | strong English retrieval quality |
| `snowflake-arctic-embed` | several sizes, up to about 335M | about 512 tokens | English | tuned specifically for search |
| `bge-m3` | about 567M | about 8,000 tokens | 100+ languages | multilingual retrieval |
| `embeddinggemma` | about 300M | about 2,000 tokens | 100+ languages | a newer multilingual model |
| `qwen3-embedding` | 0.6B up to 8B | very long | 100+ languages | highest quality, heaviest to serve |

- What separates them for this system: language (whether line workers ask in a local language while the SOPs are in English, which needs a multilingual model) and retrieval quality on the test questions. Passage length does not separate them, because each passage is one short numbered rule.
- Shortlist to evaluate (agreed 2026-10-10), one from each distinct group: `all-minilm` (small, fast baseline, to show how much a bigger model buys), `nomic-embed-text` (general default), `mxbai-embed-large` (strongest English-only option), `bge-m3` (multilingual option). Left out but considered: `snowflake-arctic-embed` (close to `mxbai-embed-large`), `embeddinggemma` (close to `bge-m3`), `qwen3-embedding` (much heavier to serve than the task needs).
- Evaluation result (2026-10-10): 21 questions (7 direct, 10 reworded, 4 exact term) against 30 passages, run inside the container with models served by Ollama on a GPU. A hit means the section holding the answer is in the top K results.

| Model | Top 1 | Top 3 | Top 5 | Time per question |
|---|---|---|---|---|
| `all-minilm` | 15/21 | 20/21 | 20/21 | 42 ms |
| `nomic-embed-text` | 16/21 | 19/21 | 20/21 | 79 ms |
| `mxbai-embed-large` | 16/21 | 20/21 | 20/21 | 169 ms |
| `bge-m3` | 17/21 | 20/21 | 21/21 | 138 ms |

  - The models are close: the gaps are one or two questions out of 21, which is too few to call one model clearly better on quality.
  - `bge-m3` was the only model to find every answer within the top 5. The other three all missed the same reworded question ("Nobody answered my request to scrap a part, what now?"), returning scrap rules instead of the response-time rule.
  - Exact-term questions (names, titles, shift hours) scored 4/4 within the top 3 on every model, so this test gives no evidence that keyword search is needed (2.10).
  - Top 1 finds the answer about 75–80% of the time and top 3 about 95%, so top-K values of 1, 3 and 5 give really different retrieval quality for the learning loop to choose between (5.3).
- Model selected: `bge-m3`.
- Why `bge-m3`:
  - Quality: it had the best score at top 1 (17/21) and was the only model to find every answer within the top 5.
  - Language: it is multilingual. On an Indian shop floor a worker may ask in Hindi or Marathi while the SOPs are in English; the English-only models cannot serve that.
- Why quality and language were chosen over speed:
  - `bge-m3` took 138 ms per question against 42 ms for the fastest model, `all-minilm`, a difference of about 0.1 second.
  - The search step is a small part of the total time: the language model that writes the answer takes seconds, so 0.1 second does not change what the worker experiences or the learning loop's reward (which subtracts latency in seconds).
  - A wrong passage costs far more than 0.1 second: it produces a wrong or unhelpful answer, a score of 0 from the worker, and possibly a wrong decision on a part.
  - The embedding model is called once per question, so its cost stays small even at ten plants; the answer-writing model dominates compute.
- Honest limit of this evidence: 21 questions is a small test, and the quality gaps between models are one or two questions. On quality alone the result would be a near tie; language support is what decides it.
- What would change it: an English-only deployment with very high question volume, where `all-minilm` gives nearly the same quality at a third of the time and a fraction of the size; or a larger test with real questions from the line showing a different ranking.
- Feeds Section G question: 1 and 4.

### 2.10 — Extras on top of plain vector search

- Date: 2026-10-10
- Options considered: keyword search alongside vector search; reranking; query rewriting; none.
- Choice: none for now. Retrieval starts as plain vector search, kept clean. The three techniques are noted as candidates, and the retrieval evaluation (2.12) decides which, if any, are added.
- Why: each extra should be justified by a measured miss, not added up front.
- Candidates to evaluate, and when each is expected to matter:
  - Keyword search alongside vector search: catches exact terms that meaning-based search can miss, such as a role title, a clause number or a part code. Cheap, with no extra model call. Expected to be the first one needed.
  - Reranking: a second model re-sorts the top results. Pays off when the store holds thousands of similar passages; costs one more model call per question.
  - Query rewriting: the model rephrases the question before searching. Helps with short or vague follow-up questions in a conversation; costs one more model call per question.
- What would change it: retrieval misses in the evaluation.
- Feeds Section G question: 1.

### 2.11 — When the search index is built

- Date: 2026-10-10
- Options considered: rebuild on every service start; only by a separate indexing command; at startup if the index is empty, plus the command.
- Choice: the service builds the index at startup only if none exists; after that, documents are added or revised through an explicit indexing command.
- Why: a first-time run works with one command and no extra step. In a plant, an SOP revision is approved and released on a date, so indexing belongs to that release step and can be recorded (who indexed which revision, and when), not to a service restart. Rebuilding on every start gets slower as the set grows.
- What would change it: to be recorded.
- Feeds Section G question: none directly.

### 2.12 — How retrieval quality is checked

- Date: 2026-10-10
- Options considered: test questions with a known answer passage; manual spot checks.
- Choice: about 20 test questions, each recorded with the numbered section that holds its answer. The score is how often that section appears in the top 1, top 3 and top 5 results. Questions are of three kinds: direct ("What is the maximum scratch length allowed?"), reworded ("The part has a long mark on the surface, can I ship it?") and exact term ("Who is the Quality Lead on night shift?").
- Why: it is repeatable and gives one number per model, so the four embedding models (2.9) are compared fairly; the same results show which top-K values are worth offering to the learning loop (5.3); and the exact-term questions show whether keyword search is needed (2.10). Spot checks give no number.
- What would change it: real question logs from the line, which would replace the written questions.
- Feeds Section G question: 1.

### 3.1 — Which language model writes the answers

- Date: 2026-10-10
- Status: open. Chosen by evaluation, the same way as the embedding model (2.9): shortlist, test on answer-quality questions, then select.
- What the model must do in production: answer only from the retrieved rule text, read tables correctly, and (from Phase 4) call tools reliably.
- Shortlist to evaluate, all served by Ollama:

| Model | Why it is in |
|---|---|
| `llama3.2` (3B) | the small, fast tier; also a candidate for the fallback model (6.8) |
| `mistral` (7B) | named in the brief; a long-standing general model |
| `llama3.1` (8B) | named in the brief; strong at tool calling |
| `qwen2.5` (7B) | named in the brief; strong at structured output and multilingual text |

- Evaluation result (2026-10-10): 19 test cases (12 with a camera result, 7 plain questions), top 5 passages, run on a local machine. Three of the four models were tested; the run was stopped during `qwen2.5` to save time, so it has no result.

| Model | Right decision | With a camera result | Plain questions | Average time per case |
|---|---|---|---|---|
| `llama3.2` (3B) | 15/19 | 9/12 | 6/7 | 35 s |
| `mistral` (7B) | 16/19 | 10/12 | 6/7 | 169 s |
| `llama3.1` (8B) | 17/19 | 10/12 | 7/7 | 112 s |

  - What is and is not measured: only whether the final decision was right. The run was stopped before the detailed results were saved, so the checks on the rule cited and the reason, and the judge model's check of the written sentences (3.9), were not completed. The times are from a development machine whose graphics card is too small for the 7B and 8B models, so they are slow here and say little about a plant server.
  - All three models failed the same two size cases: a part 2.6 mm oversize, and a good part.
  - `llama3.1` gave the one unsafe result in the test: it accepted the part that is 2.6 mm oversize, where the right result is scrap. The other two models sent that case to a person, which is wrong but safe.
  - An earlier version of the instructions to the model asked it to do three jobs at once (decide the kind of question, copy the limits, write the answer). With it, `llama3.2` got 9/19 and `mistral` 6/19. Splitting it into two simple jobs raised `llama3.2` to 15/19.
- Model selected: `llama3.1`.
- Why: it had the most right decisions and was the only one to get every plain question right. It is also one of the models the brief names.
- Known weakness, not fixed: reading the size limits. The size rule has four ranges with directions (oversize, undersize), and no model copied it out reliably. The unsafe "accept" above comes from this.
- What would change it: completing the test with `qwen2.5` and the judge, or a fix for the size-limit reading that changes the ranking.
- Feeds Section G question: 4.

### 3.2 — Whether a second language model is used

- Date: 2026-10-10
- Status: deferred, to be decided after the model evaluation (3.1), together with the slow-answer fallback (6.8).
- Options considered: decide now to use two models (a main model and a small fast backup); decide now to use one model, with a ready-made standard reply as the backup; decide after the evaluation.
- Choice: decide after the evaluation.
- Why: the evaluation of four models already includes a small one (`llama3.2`). Its measured quality and speed will show whether it is a useful backup or too weak to trust, so the decision can rest on evidence.
- Feeds Section G question: 4.

### 3.3 — How information is handed to the language model

- Date: 2026-10-10
- Options considered: everything in one block of text; each piece in its own labelled section.
- Choice: labelled sections. Instructions first, then clearly marked parts: the camera result, the SOP passages (each with its document, section and revision), any work-order details, and the question.
- Why: the model can tell a fact from the camera apart from a rule in the SOP, so it does not treat an SOP number as the measurement, and it can name the exact section it used. Labelling the SOP passages as reference text only also means a stray sentence inside a document is not followed as an instruction.
- What would change it: to be recorded.
- Feeds Section G question: 5.

### 3.4, 3.5 — What an answer looks like, and whether it names its source

- Date: 2026-10-10
- Options considered: a plain sentence only; a fixed form with boxes only; both together.
- Choice: both. Every answer has a short sentence for the worker and fixed boxes for the system: the decision (for example accept, rework, scrap, escalate), the reason, and the rule used.
- 3.5 is decided with it: the "rule used" box names the document, section and revision (for example SOP-01, section 1.2, revision 4), so every answer names its source.
- Example: message "The scratch is 12 mm long. That is more than 10 mm, so polish the part."; decision "rework"; rule "SOP-01, section 1.2".
- Why: there are two readers. The worker needs a clear sentence. The system must know for certain when the decision is "scrap" or "escalate" so it can stop and wait for a person, and a program cannot reliably pick a decision out of a sentence. The rule box lets the worker and an auditor check the answer against the document.
- What would change it: to be recorded.
- Feeds Section G question: 2 and 5.

### 3.6 — What the system does when no rule answers the question

- Date: 2026-10-10
- Options considered: the model answers from its general knowledge; the system says it has no rule and stops; the system says it has no rule and proposes sending the question to a person; the system says it has no exact answer and adds recommendations, taken either from the SOP documents or from the model's general knowledge.
- Choice: the system says it does not have an exact answer, then shows the closest related rules from the SOP documents, clearly marked as related and not as the answer, and names the person to ask. Recommendations come from the SOP documents only, never from the model's general knowledge.
- Example: for "What is the limit for a dent?", the answer is "I don't have an exact rule for dents. These related rules may help: SOP-01 section 1.2 covers surface scratches, and SOP-03 section 3.3 says tolerance questions go to the Quality Lead. I suggest confirming with the Quality Lead on shift."
- Why: it is more helpful than a plain "I don't know", and every line can still be traced to a plant document. General advice from the model sounds useful but is not this plant's rule, and a worker in a hurry may ship or scrap a part because of it.
- What would change it: to be recorded.
- Feeds Section G question: 5.

### 3.7 — Who checks a measurement against the limit

- Date: 2026-10-10
- Options considered: the language model compares the measurement with the limits and writes the answer; the model reads the limits out of the rule text and ordinary code does the comparison; the model decides and code double-checks, sending disagreements to a human.
- Choice: the model reads the limits from the retrieved rule text, and ordinary code compares the measurement with them. The limits the model read are saved in the record so a person can check them.
- Why: whether a part is acceptable is a yes-or-no check on numbers. Code never gets a comparison wrong; language models sometimes do, especially near a limit ("12 mm is within 10 mm"), and a wrong comparison ships a bad part. The limits still live only in the SOP (2.4), because the model reads them from the retrieved text each time.
- What the brief says: nothing on who does the comparison. It gives "Is this within tolerance?" as an example query, asks for tolerance specs in the knowledge documents and grounded generation from them, and in Section G question 2 asks for one part of the system that should not be agentic. This choice is consistent with all of those.
- What would change it: the model misreading limits from the text in evaluation, which would call for a structured limits table (the third option in 2.4).
- Feeds Section G question: 2.

### 3.7a — A measurement very close to a limit

- Date: 2026-10-10
- Options considered: compare the numbers as they are; flag a reading that is within the camera's measuring error (0.5 mm) of a limit and send it to a person.
- Choice: flag it. When a reading is within 0.5 mm of any limit that applies to that defect, the system does not decide. It says the camera reading alone cannot decide, asks for confirmation with a calibrated caliper, and escalates to a person. This matches SOP-01 section 1.6.
- Why: the camera can be wrong by up to 0.5 mm, so a scratch read as 9.8 mm against a 10 mm limit could really be 10.3 mm. Comparing the numbers as they are would make the system sound certain when the camera cannot tell. The 0.5 mm value is the camera's own measuring error (2.4a), not an acceptance limit.
- Consequence found while building: for size, the SOP limits are at 1.0 mm and 2.0 mm, so every size deviation between 0.5 mm and 2.5 mm is within 0.5 mm of one of them and is escalated. The camera can clear a part as "no measurable deviation" or reject a part more than 2.5 mm off, but it cannot decide the rework range on its own. This is direct evidence for the risk that the camera is too coarse for a 1.0 mm tolerance.
- What would change it: a camera several times finer than the tolerance, which would shrink the flagged band to a small fraction of the range.
- Feeds Section G question: 5, and 2.

### 3.8 — Whether the same question always gets the same answer

- Date: 2026-10-10
- Options considered: the model's randomness ("temperature") at zero, so the same input gives the same answer; some randomness, so wording varies.
- Choice: randomness at zero.
- Why: the same part should always get the same decision. If an auditor asks why the system said "rework", the case can be run again with the same result, and two workers with the same part get the same instruction. Natural-sounding variety has no value on a shop floor.
- What would change it: to be recorded.
- Feeds Section G question: 5.

### 3.9 — How answer quality is checked

- Date: 2026-10-10
- Options considered: a test with known correct answers, marked by a program; a person reading and judging answers; an LLM as judge, either a local model or a cloud model (Claude); a combination.
- Choice: three checks together.
  1. A program scores the boxes (decision, rule used, limits read) against known correct answers, on about 15 test cases.
  2. A local LLM, larger than and different from the four models being tested, judges the sentence: does it say only what the cited rule says?
  3. A few answers are read by a person as a spot check. This reading is informal and is not part of the recorded results.
- The test cases include the hard ones: a measurement just under and just over a limit, the two documents that disagree about a 22 mm scratch, and a question with no rule.
- Why each part:
  - The boxes have one exact correct answer, so a program is more reliable than any judge and gives a repeatable score.
  - The sentence has no single correct wording, so it needs a judge who can ask whether it is faithful to the rule.
  - The judge is a local model because the brief says "No managed cloud AI APIs ... everything runs on open-source/local tooling", and because a reviewer can then repeat the evaluation. A cloud model as judge would be stronger but cannot be reproduced by the reviewer and goes against the spirit of that rule.
  - The judge is a different and larger model than those tested, because a model judging its own answers tends to be too lenient.
  - A human spot check catches what both automated checks miss, such as an answer that is correct but confusing.
- What the brief says: nothing on how answers are judged; only the local-tooling rule above applies.
- What would change it: a large test set built from real questions on the line, where human-labelled answers would replace the LLM judge as the reference.
- Feeds Section G question: 1 and 4.

### 3.9a — Whether the evaluation uses a framework

- Date: 2026-10-10
- Options considered: an evaluation framework (RAGAS, DeepEval, promptfoo); our own small test script.
- Choice: our own small test script.
- Why the framework was dropped for now:
  - It is built around large cloud models as the judge. Each ready-made score runs several long built-in prompts, and with a smaller local judge those scores become unstable from run to run.
  - Its scores are hard to explain. A number such as "faithfulness 0.82" comes from prompts we did not write, so we could not tell a reviewer exactly what it measures or why one answer lost points.
  - It solves a problem we do not have yet. Its strengths are reports, dashboards and running thousands of cases automatically; we have about 15 cases.
  - It adds a large dependency and setup work for a check that is small.
- Why our own script was chosen:
  - The check is simple: compare the boxes with the known correct answers, then ask the judge one yes-or-no question about the sentence. That is about 100 lines.
  - Every step is visible. A reviewer can read exactly how each answer was marked and re-run it.
  - The judge's question is ours, so it can be worded for this task ("does the sentence say only what the cited rule says?") and kept short enough for a local model to answer reliably.
- What would change it: production use with hundreds of real questions and tests that run automatically on every change. At that point a framework such as RAGAS or DeepEval earns its place, because its reports and standard scores save more work than they cost to explain.
- Feeds Section G question: 4.

### 3.9b — Which model is the judge

- Date: 2026-10-10
- Options considered: `gemma3` (12B, Google); `phi4` (14B, Microsoft); `qwen2.5` (14B, Alibaba).
- Choice: `gemma3` (12B), served by Ollama.
- Why: the judge must be larger than the four tested models and different from them. The tested models come from Meta, Mistral and Alibaba; `gemma3` is from a maker none of them share, so it has no reason to favour one, and it handles several languages. `qwen2.5` (14B) is the same family as one tested model and may favour it. `gemma3` has open weights and is free to download and run locally, so it follows the brief's local-tooling rule.
- What would change it: the judge disagreeing with the human spot check, which would call for a stronger judge or a clearer judging question.
- Feeds Section G question: none directly.

### 4.1 — A ready-made agent toolkit, or our own agent loop

- Date: 2026-10-10
- Options considered: a ready-made toolkit (LangChain or LlamaIndex); our own loop in plain Python.
- Choice: our own loop in plain Python. The loop asks the model what to do next, does it, writes down the step and the reason, and repeats.
- Why:
  1. The brief grades the step record. It says the trace must show "which tool, in what order, and why", that "the model just decided" is not an acceptable audit answer, and it lists "the clarity and correctness of the agent's decision trace" as an evaluation point. In our own loop, our code writes each step into the record as it happens, so the record cannot be incomplete.
  2. Safety rules must be impossible to skip. The brief says an "escalate" or "scrap" result must be returned as a proposed action, never executed. In our own loop that is one fixed check every answer passes through. In a toolkit it is an add-on that depends on how the toolkit calls it.
  3. The brief allows it. It lists the choice as "LangChain, LlamaIndex, or native Python — your call", so plain Python is an accepted option, not a shortcut.
  4. Small local models make mistakes in their replies: a badly formed step, or a tool that does not exist. We need to decide what happens then (try again, or send to a person). In our own loop we control that; in a toolkit that handling is built in and harder to change.
  5. The agent is small: four tools and a few steps, about 100 lines of plain Python. A toolkit adds a large library whose way of working changes often between versions, which means more upkeep in a real plant.
  6. It supports Section G question 2. The number check, the approval gate and the record are plain code that can be pointed to line by line; only the choice of tool is left to the model.
- Why the toolkit was not chosen: it runs the loop inside its own code. Its step record comes in its own format and would have to be caught and converted; the "why" is whatever text the model happened to give; and the best tracing tools for these toolkits are cloud services, which the brief does not allow. It can be done, but the time would go into bending the toolkit to our record format.
- Honest cost: we write and maintain the loop ourselves, and a team that already knows LangChain would find a toolkit version more familiar.
- What would change it: an agent with many tools, memory across conversations, or several agents working together, where a toolkit's ready-made parts would save more work than they cost to adapt.
- Feeds Section G question: 2.

### 4.2 — How the model states which tool it wants

- Date: 2026-10-10
- Options considered: the model writes a sentence and code picks the tool name out of it; the model fills in a fixed form (structured output).
- Choice: structured output. At each step the model fills in a small form: which tool, what to give it, and why. It can only pick a tool from our list. Ollama enforces the form, the same way it does for answers (3.4).
- Why: a sentence can be worded many ways and code can misread it; a fixed form cannot be misread, the model cannot invent a tool, and the "why" the brief asks for is always present. It also gives the main simplicity a toolkit would offer, which is one reason the toolkit is not needed (4.1).
- What it would take to switch to a toolkit later: the four tools are plain functions with clear inputs and outputs, and the model sits behind one small interface, so they can be wrapped as toolkit tools unchanged. The roughly 100-line loop would be replaced by the toolkit's agent, and a hook would be added to copy each toolkit step into our audit record. The number check, the approval gate and the audit record stay outside the toolkit as they are.
- What would change it: to be recorded.
- Feeds Section G question: 2.

### 4.3, 4.4 — A broken or repeating step, and the limit on steps

- Date: 2026-10-10
- Options considered: keep trying until the model produces a usable step; allow a small number of steps, then stop and send the case to a person.
- Choice: a limit on steps (5 by default, held as a setting). When the limit is reached, or the model keeps asking for the same thing, the agent stops, tells the worker it could not work the case out and to ask their supervisor, and returns this as a proposed escalation. The record shows every step that was taken.
- Why: a loop with no limit may never finish, and a line worker cannot wait. A case the system cannot resolve is exactly the kind that should go to a person, and the record of the failed steps helps find out why.
- What would change it: to be recorded.
- Feeds Section G question: 2 and 5.

### 4.5 — The tools the model can choose from

- Date: 2026-10-10
- Options considered: the four tools the brief names; those four plus a fifth, "ask the worker".
- Choice: five tools.
  - Check the photo: finds the defect type, measures it, and reads the ID on the part.
  - Search the rules: finds the right SOP passages and gives the answer or the limit check.
  - Check the work order: looks up the status of a work order (a mock lookup, as the brief asks).
  - Send to a person: proposes that a supervisor or quality lead decides.
  - Ask the worker: asks the worker one question when the request is unclear.
- Why: the brief requires the first four. The fifth follows from the choice to keep a conversation (4.10): when it is not clear what the worker wants, asking is better than guessing.
- What would change it: to be recorded.
- Feeds Section G question: 2.

### 4.6 — What the mock work-order lookup returns

- Date: 2026-10-10
- Options considered: a very small lookup that only says open or closed; a fuller one.
- Choice: the fuller one, with about six mock work orders. For each it returns the status (open, in inspection, on hold, in rework, closed, scrapped), the part type, how many times the part has been reworked, and whether it is a priority order. An unknown number returns "not found".
- Why: it lets the system use rules already in the SOPs. For example, SOP-02 says a part may be reworked once, so a work order that already shows one rework changes what the system should say.
- What would change it: a real ERP connection, which would replace the mock.
- Feeds Section G question: none directly.

### 4.7 — Who decides whether a sent photo is checked

- Date: 2026-10-10
- Status: decided. A safety check that would force the photo to be looked at was proposed and not taken: the model is left to choose. The risk this leaves is on the risk list.
- Options considered: the photo is always checked as a fixed first step; the model chooses its tools, including the photo tool; the model chooses, with a safety check that a sent photo cannot be skipped.
- Choice: the model chooses the tools and takes the decisions. When it is not clear what the worker wants from a photo, the model may ask the worker, then pick the relevant tool.
- Why: the brief's Section D says the model decides, per query, whether to answer from the SOPs, use the photo tool, check the work order, or escalate. A fixed first step would take that choice away from the model.
- What the brief says: the photo tool is one of the four choices the model makes.
- Feeds Section G question: 2.

### 4.8 — Who can decide to send a case to a person

- Date: 2026-10-10
- Options considered: fixed rules only; fixed rules, and the model may also choose it.
- Choice: both. The fixed rules in code always apply: a crack, a reading too close to a limit, two documents that disagree, and the model getting stuck. On top of that, the model may choose "send to a person" when it is unsure, and it must give its reason, which is saved in the record.
- Why: fixed rules are predictable but cannot cover every case. An extra call to a supervisor costs a few minutes; a wrong guess the model was unsure about can cost a part.
- What would change it: the model escalating so often that supervisors stop paying attention, which would call for tighter instructions or a limit.
- Feeds Section G question: 2 and 5.

### 4.9 — Who writes the record of the steps

- Date: 2026-10-10
- Options considered: the model describes what it did after it finishes; our program writes down each step as it happens.
- Choice: our program writes each step as it happens. For every step it saves the step number, which tool was used, what was given to it, what came back, and how long it took. The model's own reason for choosing that step is saved next to it. The model cannot change or skip anything in the record.
- Why: a description written afterwards from the model's memory can leave a step out or report one that did not happen. A record written by code as each step runs is a fact, and it is what the brief asks for: "which tool, in what order, and why".
- What would change it: to be recorded.
- Feeds Section G question: 2 and 5.

### 4.10 — Whether the system remembers a conversation, and where it is stored

- Date: 2026-10-10
- Not in the original roadmap; raised while discussing how the model asks the worker a question.
- Options considered for memory: no memory, each question stands alone (as the brief's API describes); memory within one conversation, so the model can ask the worker a question and use the reply.
- Choice for memory: memory within one conversation. Messages are linked by a conversation number.
- Options considered for storage: the SQL database already used for the audit records; MongoDB.
- Choice for storage: MongoDB, in its own container.
- What speaks for MongoDB: a conversation is naturally one document holding a list of messages, which is the shape MongoDB stores; it handles very large volumes of chat; and messages with mixed content (several photos, voice notes) need no fixed table. It is open-source and runs in Docker, so it follows the brief's local-tooling rule.
- What it costs: two databases to run, back up and explain. Audit records are in SQL and conversations in MongoDB, so linking a message to the decision it led to needs the transaction number stored on both sides. The "no edits, no deletes" protection built for the SQL audit tables does not cover MongoDB and has to be handled separately.
- Recommendation that was not taken: keep conversations in the SQL database, as one more table. Recorded so the trade-off is visible.
- Why (in the owner's words): "it fits the shape of a conversation better".
- What would change it: to be recorded.
- Feeds Section G question: 4 and 5.

### 5.1 — The learning method

- Date: 2026-10-10
- Options considered: an epsilon-greedy contextual bandit; simple Q-learning (the two the brief allows).
- Choice: an epsilon-greedy contextual bandit. For each defect type the system keeps an average score for each setting. Most of the time it uses the setting with the best average; now and then it tries another, in case that one has become better. After each thumbs up or down it updates the average.
- Why: there is one choice per question, and one question does not change the next one. Q-learning is made for chains of steps where each choice changes the next situation; with no chain it works out as the same method with extra parts. The bandit fits the task and is simple to explain.
- What would change it: a setting whose effect carries over from one step to the next, for example one that changes how a multi-step conversation unfolds.
- Feeds Section G question: the action-axis justification (Section E).

### 5.2 — Which setting the learning loop tunes

- Date: 2026-10-09
- Status: provisional ("ok with this for now"); revisit when Phase 5 starts.
- Options considered: OCR engine; RAG top-K.
- Choice: RAG top-K.
- Why: it affects every query, including text-only ones; it needs no second OCR engine in the image; it directly changes answer quality, which is what feedback measures; and the best value plausibly differs by defect type (a crack needs tolerance, scrap and escalation rules together, while "no defect" needs one passage).
- What would change it: finding that the latency and feedback differences between top-K values are too small to produce a visible shift, or that OCR accuracy turns out to be the main cause of unhelpful answers.
- Feeds Section G question: the action-axis justification (Section E).

### 5.3 — The values the learning loop chooses between

- Date: 2026-10-10
- Options considered: 1, 3 and 5 passages; 3, 5 and 8 passages.
- Choice: 1, 3 and 5 passages. This also confirms decision 5.2: the setting being tuned is the number of passages (RAG top-K).
- Why: the retrieval test (2.9) showed the right rule is found about 17 times out of 21 with 1 passage, 20 with 3 and 21 with 5. These values behave clearly differently, so the system has something real to learn: with 1 the rule is sometimes missing, with 5 it is always there but the model has more to read. With 3, 5 and 8 the rule is almost always found, so the three would behave nearly the same and little would be learned.
- What would change it: a larger document set, where the useful range of values moves higher.
- Feeds Section G question: the action-axis justification (Section E).

### 5.4 — How often the system tries a setting that is not its current best

- Date: 2026-10-10
- Options considered: a fixed rate of about 1 time in 10; a high rate at first that shrinks until it almost stops.
- Choice: a fixed rate of 1 in 10 (epsilon = 0.1), held as a setting.
- Why: in a plant the rule books keep changing, so the best setting can change too. A fixed rate keeps checking forever and notices such a change. A shrinking rate learns fast at the start but, once settled, may not notice when things change.
- What would change it: a stable environment where every weaker answer is costly, which would favour a shrinking rate.
- Feeds Section G question: the action-axis justification (Section E).

### 5.5 — How the score for each setting is kept

- Date: 2026-10-10
- Options considered: a plain average of every result so far; recent results count more.
- Choice: recent results count more. Each new result moves the score a fixed small amount toward it (a constant step size, held as a setting), so old results slowly fade.
- Why: the rule books keep changing (the same reason as 5.4), so the best setting can change. With a plain average, after a thousand answers one new result barely moves the score and the system is slow to notice. The cost is that the score moves around a little more.
- What would change it: a stable environment, where a plain average gives a steadier score.
- Feeds Section G question: the action-axis justification (Section E).

### 5.7 — Which waiting time counts in the score

- Date: 2026-10-10
- Options considered: the whole wait, from the worker pressing send to getting the answer; only the part the setting changes (searching and the model reading the passages).
- Choice: the whole wait.
- Why: it matches the brief's wording, "(feedback score × 10) − (latency in seconds)", and it is what the worker actually experiences. The cost is that it includes time the setting cannot change, such as checking the photo, which makes the scores noisier.
- What would change it: scores so noisy that the system cannot tell the settings apart, which would call for counting only the part the setting changes.
- Feeds Section G question: the action-axis justification (Section E).

### 5.8 — How many times feedback counts for one answer

- Date: 2026-10-10
- Options considered: only once per answer; as many times as the worker presses.
- Choice: only once. The first thumbs up or down counts; a second one for the same answer is refused with a clear message. Feedback for an unknown answer is refused too.
- Why: each answer should count exactly once in the learning. A worker pressing thumbs down five times in frustration would otherwise count as five bad answers and wrongly push the system away from a good setting.
- What would change it: to be recorded.
- Feeds Section G question: 5.

### 5.9 — Where the score sheet is kept

- Date: 2026-10-10
- Options considered: in memory only; in the SQL database.
- Choice: in the SQL database. The scores are saved after every update, and each change is also saved as a new row.
- Why: a restart loses nothing that was learned, and the saved changes give the history needed for the log or plot in the README. The scores are small, structured numbers, which is what the SQL database is for (0.4).
- What would change it: to be recorded.
- Feeds Section G question: none directly.

### 5.10 — How the learning is shown

- Date: 2026-10-10
- Options considered: made-up feedback from a rule we write (for example "5 passages gets a thumbs up 80% of the time"); real results, replayed.
- Choice: real results, replayed. The real test cases are run through the real system once with 1 passage, once with 3 and once with 5. For each run it is noted whether the answer was right (thumbs up) or wrong (thumbs down) and how long it took. Those real results are then replayed a few hundred times, with a fixed random seed, and the log or plot shows what the system learns.
- Why: with made-up feedback we would be inventing the result, and the system would only learn the numbers we typed in. With replay, every thumbs up or down comes from an answer the system really gave, so the learning shown is honest and can be repeated.
- Limit: the thumbs come from a program checking the answer against the known correct result, not from a person's opinion of helpfulness.
- What would change it: real feedback from workers on the line, which would replace the replay.
- Feeds Section G question: the action-axis justification (Section E).

### 5.10a — Slow answers on the local machine in the learning demonstration

- Date: 2026-10-10
- The problem: the score is (thumbs up × 10) − seconds waited. On the development machine an answer takes 55 to 120 seconds, because its graphics card is too small for the chosen model. A right answer then scores about −100 and a wrong one about −110, so the waiting time swamps the thumbs up and the system would only learn "fewer passages is faster".
- Options considered: show the demonstration with the raw local seconds; adjust the time so the demonstration reflects the hardware a plant would use.
- Choice: adjust the time for the demonstration. The real answer times are measured on the local machine and saved as measured. In the replay they are divided by a stated factor (`--time-scale`), so a local answer of about 100 seconds counts as a few seconds, as it would on a plant server. The service itself is not changed: `/feedback` uses the brief's formula with the real seconds, and the factor defaults to 1.
- Why: the brief's formula balances a thumbs up (10 points) against a wait of a few seconds. That balance only exists when answers take seconds, not minutes. Dividing the time keeps the real differences between the settings (more passages is still slower by the same proportion) while restoring the balance the formula was designed for.
- What is honest to say: the right-or-wrong results and the relative speed of the settings are real; the absolute seconds in the replay are scaled, and the README states the factor used. A run with the raw seconds is shown next to it.
- Result (2026-10-10): 57 real answers were collected with `llama3.1` (19 cases at 1, 3 and 5 passages). Right answers: 15/19 with 1 passage, 16/19 with 3, 16/19 with 5. Average time: 29 s, 67 s and 85 s. Replayed for 600 rounds with seed 7 and the seconds divided by 20:
  - `surface_scratch` shifted from 1 passage (25 of the first 30 questions) to 3 passages (27 of the last 30), because one scratch case is wrong with 1 passage and right with 3.
  - `dimensional_deviation` shifted from 3 passages (20 of the first 30) to 1 passage (26 of the last 30), because the answers are equally right at every value and the fastest wins.
  - `crack` and `no_defect` stayed on 1 passage; `no_image` settled on 3.
  - With the raw seconds, every defect type with a photo stayed on 1 passage throughout, the wrong-answer setting winning on speed alone. This confirms the problem the factor addresses.
  - Limits: few cases per defect type (one each for `crack` and `no_defect`), marks from a program and not a worker, and a quality difference of one case in nineteen.
- What would change it: running on hardware where the model answers in a few seconds, which removes the need for any factor.
- Feeds Section G question: the action-axis justification (Section E).

### 5.11 — Whether the record says the system was trying another setting

- Date: 2026-10-10
- Options considered: record only which setting was used; also record whether it was the best known setting or a try of another one.
- Choice: record it. Each record says "best_known" or "trying_another" next to the number of passages used.
- Why: about 1 answer in 10 uses a setting that is not the current best and may be a little weaker. If someone later asks why a worker got a weaker answer, the record explains it. It costs one extra word.
- What would change it: to be recorded.
- Feeds Section G question: 5.

### 6.1 — What the record keeps about the photo

- Date: 2026-10-10
- Options considered: only the file name; the whole photo inside the record; a fingerprint of the photo in the record, with the photo itself stored with the conversation.
- Choice: a fingerprint (a SHA-256 hash) of the photo in the audit record, next to the file name. The photo itself is stored with the conversation in MongoDB (4.10).
- Why: a file name proves nothing, because two different photos can share a name. The whole photo would make the record table heavy and slow. A fingerprint is short, the same photo always gives the same one, and any change to the photo changes it, so it can be proved later that the stored photo is exactly the one the system looked at.
- What would change it: a rule that photos must not be kept at all, in which case only the fingerprint would remain.
- Feeds Section G question: 5.

### 6.2 — How strongly the record book is protected from being changed

- Date: 2026-10-10
- Options considered: keep the database rule that refuses edits and deletes; add a chain of fingerprints on top of it.
- Choice: add a chain of fingerprints. Each new record stores the fingerprint of the record before it. A check walks the chain and reports whether any record was changed or removed.
- Why: the database rule stops normal mistakes and misuse, but a person with full access to the database could switch the rule off, change a record and switch it back on, and nobody would know. With the chain, changing or removing an old record makes every fingerprint after it stop matching, so tampering is detected.
- Recommendation that was not taken: keep the rule only and describe the chain as a future step. Building it gives a stronger audit trail now.
- Limit: the chain detects tampering; it does not prevent it. Someone who can rewrite the whole chain from the changed record onward would still go unnoticed unless the latest fingerprint is also kept somewhere outside the database.
- What would change it: to be recorded.
- Feeds Section G question: 5.

### 6.3 — Whether feedback and approval events are logged too

- Date: 2026-10-09
- Options considered: update the original decision record when feedback or an approval arrives; store each as a new row linked to the transaction.
- Choice: feedback and approvals are stored as new rows, never as edits. The current status of a transaction is worked out from its events.
- Why: nothing in the audit trail is ever changed, so the audit table can reject every edit and delete, and the full history of who did what and when is kept.
- What would change it: to be recorded.
- Feeds Section G question: 5.

### 6.4 — Which results wait for a supervisor

- Date: 2026-10-10
- Options considered: only "scrap" and "send to a person" wait; "rework" waits too.
- Choice: only "scrap" and "send to a person" wait for approval. "Accept", "rework" and plain information do not.
- Why: this is exactly what the brief asks. Scrap cannot be undone, so it must wait. Rework can be checked again or repeated, so nothing is lost. If supervisors were asked about every small polish they would start approving without looking, and the approval step would lose its value.
- What would change it: a part or customer where rework itself is costly or limited, which would make rework worth approving too.
- Feeds Section G question: 5.

### 6.5 — How a supervisor approves or rejects a proposed action

- Date: 2026-10-10
- Options considered: a "waiting for approval" note in the answer only; a small approval step in the system.
- Choice: a small approval step. One more endpoint (`/approvals`) takes "approve" or "reject", the supervisor's name and a short note. It is saved as a new record linked to the original answer (6.3), and the status changes from waiting to approved or rejected.
- What the brief says: "Any agent path that ends in 'escalate' or 'flag for scrap' must be returned as a proposed action, not an executed one — the API should never auto-post anywhere without a simulated human-approval step." It names the approval step but does not say how to build it. A note alone would meet the minimum wording, because the system never posts anything onward; it would not show the step working.
- Why: a reviewer can try the full path (ask, get a proposal, approve it, see it in the record), and the approval becomes part of the audit trail. It is a fourth endpoint on top of the three the brief requires.
- What would change it: a real approval system in the plant (for example in the ERP), which this step would hand over to.
- Feeds Section G question: 5.

### 6.6 — How long a proposed action can wait

- Date: 2026-10-10
- Options considered: it waits for ever; it waits for a set time and is then marked "overdue".
- Choice: a proposed action has one of four statuses: waiting for approval, overdue, approved or rejected. It becomes overdue after a set time (30 minutes by default, held as a setting) if nobody has acted. An overdue proposal can still be approved or rejected, and it is never carried out without a person.
- Why: a proposal nobody answers leaves a part on hold, which is a real problem on a shop floor; marking it makes the problem visible. SOP-03 section 3.4 gives the supervisor 30 minutes for a scrap request before it goes to the Plant Quality Manager.
- Weakness: the 30 minutes is in the SOP and also in this setting, so the two could drift apart if the SOP is revised.
- What would change it: to be recorded.
- Feeds Section G question: 5.

### 6.7 — The time limit before the system gives up on the model

- Date: 2026-10-10
- Options considered: 10 seconds; 30 seconds; longer.
- Choice: the limit is a setting. In this repository it defaults to 300 seconds, because development and review happen on a local machine where the larger models are slow. It was first set to 120 seconds; in the fresh-start test the first photo question took 128 seconds on the development laptop and got the ready-made reply, so it was raised. The value intended for a real plant is 10 seconds.
- Why 10 seconds for a plant: the score is 10 points for a thumbs up minus the seconds waited, so after 10 seconds even a good answer scores zero or less; waiting longer cannot pay off. It also suits a worker standing at a machine with a part in hand.
- Why longer locally: on the development machine the larger models take well over 10 or 30 seconds, so a short limit would replace almost every answer with the ready-made reply and the rest of the system could not be shown working.
- How it is applied: the limit covers the whole request. Each call to the model is given only the time that is left; when it runs out the call is dropped and the ready-made reply (6.8) is returned. The slow call is not tried again.
- What would change it: measured answer times on the plant's own hardware.
- Feeds Section G question: 4.

### 6.8 — What the worker gets when the model is too slow

- Date: 2026-10-10
- Options considered: a smaller, faster model; a ready-made reply with the matching rule passages attached; a saved earlier answer.
- Choice: a ready-made reply with the rule passages attached. When the time limit is passed, the system says the assistant is taking too long, shows the SOP passages the search found, and tells the worker to ask the supervisor if unsure. No model writes anything.
- This also settles 3.2: no second language model is used.
- Why: the search step is fast and needs no large model, and the passages are the plant's own rules, so nothing can be made up and no wrong decision on a part is given. In the answer test the small model was often wrong (right for the right reason in 8 of 19 cases), so a quick answer from it could be a wrong one. A saved answer only helps for repeated questions and may be out of date after an SOP revision.
- What the brief says: "if the primary local model's response exceeds a latency ceiling you define, fall back to a smaller/faster model or a cached/templated response rather than retrying the same slow path." This is the templated response.
- What would change it: a small model that passes the answer test, which would make a quick written answer safe.
- Feeds Section G question: 4.

### 6.9 — Whether a ready-made reply counts in the learning

- Date: 2026-10-10
- Options considered: count it; leave it out.
- Choice: count it. Feedback on a ready-made reply updates the score of the number of passages that was in use when the model ran out of time.
- Why: the brief's score is built to punish slowness, and giving the model more passages does make it slower, so a setting that pushes the model past the time limit should lose points for it. The weakness is that the thumbs up or down is about the ready-made reply, not about a real answer.
- What would change it: timeouts caused mostly by things unrelated to the setting (for example a busy server), which would make these results noise.
- Feeds Section G question: the action-axis justification (Section E).

### 6.10 — Whether answers are saved and reused (caching)

- Date: 2026-10-10
- Status: not used for now; to be looked at again later.
- Options considered: no caching; save and reuse whole answers; save only the limits the model read from each rule passage, and still do the number check fresh for each part.
- Choice: no caching for now. Every question is worked out fresh from the current rule book.
- Noted for later: saving only the limits read from each passage, thrown away when that passage is revised, would remove most model calls for photo checks without the risk of showing a stale answer. It is a candidate for the first cost saving when scaling to ten plants.
- Why whole answers are risky to reuse: an old answer could be shown after a rule book has changed, or an answer for one part shown for a different part.
- Feeds Section G question: 4.

## Risks noticed, not solved

- Measurements from a photo depend on a known camera scale. On a real line that needs a fixed camera position or a calibration target; without it, a "within tolerance" answer could be wrong while looking precise. (Noticed at decision 1.4.)
- A misread ID can still look valid. On the hard set, 3 of 100 IDs were read with one wrong digit (for example `WO-38522` for `WO-38322`) and passed the format check, so a defect could be recorded against the wrong work order. Closing it needs a check digit in the ID, or a cross-check that the work order exists and is at that station. (Noticed in Phase 1 evaluation.)
- The ID is assumed to be stamped in a fixed area, and defects are generated outside it. A crack or scratch that crosses the ID is neither detected as a defect nor read reliably. (Noticed in Phase 1 build.)
- The camera's measuring error (about 0.5 mm) is half of a typical 1.0 mm size tolerance. Measurement practice expects the instrument to be several times finer than the limit it checks, so a part near the limit could be accepted or rejected wrongly. Closing it needs a higher-resolution camera or lens for size checks, or a gauge for parts that measure close to the limit. (Noticed at decision 2.4a.)
- The model chooses whether to look at a sent photo (decision 4.7), so it can skip one. If it answers from the SOPs alone while the photo shows a crack, the crack is never seen. Closing it needs a rule that a sent photo is always inspected, or a check that stops the model finishing without it. (Noticed at decision 4.7.)

## Found in the whole-system test (2026-10-10)

The whole system was run with a real model (`llama3.1`), MongoDB and all parts together: a photo with approval and feedback, a plain question, a conversation with a follow-up, a work-order question and a question with no rule.

Fixed after the test:

- The model looked up the same work order five times and gave up. A repeated photo check or work-order lookup is now refused with a hint to answer the worker, and the model is told that these two tools only gather facts.
- In a follow-up message the model typed a poor search phrase, so the crack rule was not found. For a part check, the search is now built by code from the worker's words and the defect type seen, not from the model's wording.

Left open on purpose:

- The first answer for each defect type uses only 1 passage, because the learning loop tries each setting once at the start, beginning with 1. With 1 passage the question "Who is the Quality Lead on the night shift?" got "I don't have an exact rule"; with 3 it was answered correctly. The loop works as designed, but the first answers are weaker.
- The model sometimes marks a plain answer as "must go to a person". For "Who must approve a scrap decision?" it gave the right answer and also raised a proposal for a supervisor, which is not needed.
- Reading the size limits (see 3.1): no tested model copies the four-range size rule out reliably, and `llama3.1` once accepted a part that should be scrapped.

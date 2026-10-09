# ShopFloor Copilot

An AI-assisted visual inspection and SOP agent for a manufacturing shop floor. A line worker sends a photo of a part and/or a text question (for example "Is this within tolerance?" or "Who do I escalate a crack to?"), and the assistant answers using defect classification, OCR, SOP retrieval, and an agent loop that records how it reached its answer.

Everything runs on open-source, local tooling. No managed cloud AI APIs are used.

## Status

Work in progress. The repository currently holds the assignment brief and the decision-rationale outline; the implementation has not been added yet.

## Planned components

- **API** (FastAPI): `POST /inspect`, `POST /feedback`, `GET /transactions/{id}`
- **Vision and OCR**: defect classification and work-order / part-ID extraction
- **Knowledge layer**: vector retrieval over mock SOP documents, with a local LLM via Ollama
- **Agent loop**: ReAct-style tool selection with an explicit decision trace
- **Adaptive optimization**: a contextual bandit updated from user feedback
- **Governance**: append-only audit log, human approval for escalate/scrap actions, and a latency fallback

## Repository layout

| Path | Contents |
|---|---|
| [docs/](docs/) | Project documentation, including [DECISIONS.md](docs/DECISIONS.md) |
| [business_docs/](business_docs/) | The assignment brief |

## Setup

To be added with the implementation.

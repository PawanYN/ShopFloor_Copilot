# ShopFloor Copilot

An AI-assisted visual inspection and SOP agent for a manufacturing shop floor. A line worker sends a photo of a part and/or a text question (for example "Is this within tolerance?" or "Who do I escalate a crack to?"), and the assistant answers using defect classification, OCR, SOP retrieval, and an agent loop that records how it reached its answer.

Everything runs on open-source, local tooling. No managed cloud AI APIs are used.

## Status

Work in progress. The repository currently holds the assignment brief, the roadmap and the decision-rationale outline; the implementation has not been added yet.

The plan, the architecture and the open design decisions are in [docs/ROADMAP.md](docs/ROADMAP.md). Tools and approaches are chosen phase by phase and recorded in [docs/DECISION_LOG.md](docs/DECISION_LOG.md).

## Planned components

- **API**: `POST /inspect`, `POST /feedback`, `GET /transactions/{id}`
- **Vision and OCR**: defect classification and work-order / part-ID extraction
- **Knowledge layer**: vector retrieval over mock SOP documents, with a local LLM via Ollama
- **Agent loop**: ReAct-style tool selection with an explicit decision trace
- **Adaptive optimization**: a lightweight learning loop updated from user feedback
- **Governance**: append-only audit log, human approval for escalate/scrap actions, and a latency fallback

## Repository layout

| Path | Contents |
|---|---|
| [docs/](docs/) | [ROADMAP.md](docs/ROADMAP.md), [DECISION_LOG.md](docs/DECISION_LOG.md) and [DECISIONS.md](docs/DECISIONS.md) |
| [business_docs/](business_docs/) | The assignment brief |

## Setup

To be added with the implementation.

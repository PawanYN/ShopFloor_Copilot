# ShopFloor Copilot — FDE Decision Rationale

Answers to Section G of the candidate assignment (3–5 sentences each), plus the RL action-space justification that Section E asks for. Each answer is written from the entries in [DECISION_LOG.md](DECISION_LOG.md).

## 1. Vector RAG vs. vectorless / long-context read

_Why vector RAG fits this SOP corpus, and what would change if the plant's SOP set were fixed at 20 pages instead of continuously growing._

TODO

## 2. Agent loop vs. fixed pipeline

_Why an agent loop is justified for the tool-selection step, and the one part of this system that should NOT be agentic, and why._

TODO

## 3. Defect classifier: classical CV, pretrained model, or both

_Why this choice, and what would push toward fine-tuning a custom model instead._

TODO

## 4. First cost-optimization lever when scaling from one plant to ten

_Which of prompt/response caching, model tiering, batching, a smaller fine-tuned model, or quantization to apply first, and why that one before the others._

TODO

## 5. Unaddressed shop-floor governance risk

_One governance risk specific to a shop floor (not a generic AI risk) that this design does not yet fully address, and how to close it in a real engagement._

TODO

## RL action space

_Which single axis the bandit optimizes (OCR engine or RAG top-K), and why that axis over the other._

TODO

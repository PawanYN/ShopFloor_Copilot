"""Score language models on answer cases with known correct results.

    python -m app.knowledge.evaluate_answers --models llama3.2 mistral llama3.1 qwen2.5

A program marks the decision and the rule cited. A separate, larger local model
judges whether each model-written sentence says only what the passages say.
"""

import argparse
import json
import sys
import tempfile
from pathlib import Path

from app import config
from app.knowledge.answer import answer_question, search_text
from app.knowledge.documents import load_passages
from app.knowledge.index import build_index
from app.knowledge.retrieval import search
from app.knowledge.store import ChromaPassageStore, Hit
from app.llm import OllamaClient

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {"supported": {"type": "boolean"}, "reason": {"type": "string"}},
    "required": ["supported", "reason"],
}

JUDGE_PROMPT = """You are checking an assistant's answer against plant SOP passages.

Reply "supported": true only if every factual statement in the answer is found in the passages.
An answer that says no exact rule exists, describes what these passages cover, or suggests asking a role named in them, is supported.
Reply "supported": false if the answer states a rule, number, name or instruction that is not in the passages.
Give a one-sentence reason."""


def mark(case: dict, answer) -> dict:
    cited = [f"{rule['document']}#{rule['section']}" for rule in answer.rules]
    checks = {
        "decision": answer.decision in case["decisions"],
        "rule": not case["rules"] or bool(set(cited) & set(case["rules"])),
        "conflict": answer.conflict if case.get("needs_conflict") else True,
        "reason": answer.reason == case["reason"] if case.get("reason") else True,
        "contains": all(term.lower() in answer.message.lower() for term in case.get("must_contain", [])),
    }
    return {**checks, "correct": all(checks.values()), "cited": cited}


def run_model(client, model: str, cases: list[dict], retrieved: list[list[Hit]]) -> list[dict]:
    rows = []
    for case, hits in zip(cases, retrieved):
        vision = case.get("vision")
        try:
            answer = answer_question(client, model, case["question"], hits, vision)
        except Exception as error:  # a model that returns unusable output fails the case
            rows.append({"case": case["name"], "error": str(error)[:200], "correct": False})
            continue
        rows.append(
            {
                "case": case["name"],
                **mark(case, answer),
                "kind": answer.kind,
                "got": answer.decision,
                "wanted": case["decisions"],
                "message": answer.message,
                "written_by_model": not (answer.kind == "measurement_check" and vision),
                "passages": [hit.text for hit in hits],
                "invalid_citations": answer.invalid_citations,
                "rules_read": answer.rules,
                "reached_by": answer.reason,
                **answer.usage,
            }
        )
        print(f"{model}: {case['name']} -> {answer.decision} ({answer.usage['seconds']}s)", file=sys.stderr, flush=True)
    return rows


def judge(client, judge_model: str, rows: list[dict]) -> None:
    for row in rows:
        if not row.get("written_by_model") or not row.get("message"):
            continue
        passages = "\n\n".join(row["passages"])
        reply = client.chat_json(
            judge_model, JUDGE_PROMPT, f"## SOP passages\n{passages}\n\n## Answer to check\n{row['message']}", JUDGE_SCHEMA
        )
        row["judge_supported"], row["judge_reason"] = reply.data["supported"], reply.data["reason"]
        print(f"judge: {row['case']} -> {reply.data['supported']} ({reply.seconds}s)", file=sys.stderr, flush=True)


def report(results: dict[str, list[dict]]) -> None:
    print(f"{'model':<12} {'correct':>8} {'decision':>9} {'rule':>6} {'judge yes':>10} {'sec/case':>9} {'prompt tok':>11} {'output tok':>11}")
    for model, rows in results.items():
        done = [row for row in rows if "error" not in row]
        judged = [row for row in done if "judge_supported" in row]
        mean = lambda key: sum(row[key] for row in done) / len(done) if done else 0
        judge_text = f"{sum(r['judge_supported'] for r in judged)}/{len(judged)}" if judged else "n/a"
        print(
            f"{model:<12} {sum(r['correct'] for r in rows):>5}/{len(rows):<2} "
            f"{sum(r.get('decision', False) for r in rows):>6}/{len(rows):<2} "
            f"{sum(r.get('rule', False) for r in rows):>3}/{len(rows):<2} {judge_text:>10} "
            f"{mean('seconds'):>9.1f} {mean('prompt_tokens'):>11.0f} {mean('completion_tokens'):>11.0f}"
        )
    for model, rows in results.items():
        for row in rows:
            if "error" in row:
                print(f"\nerror  {model}: {row['case']}: {row['error']}")
            elif not row["correct"]:
                failed = [name for name in ("decision", "rule", "conflict", "reason", "contains") if not row[name]]
                print(f"\nwrong  {model}: {row['case']}: failed {failed}; got {row['got']} ({row['kind']}), wanted {row['wanted']}, cited {row['cited']}")
            if row.get("judge_supported") is False:
                print(f"\njudge  {model}: {row['case']}: {row['judge_reason']}\n       answer: {row['message']}")


def save(path: str, results: dict[str, list[dict]]) -> None:
    Path(path).write_text(json.dumps(results, indent=2), encoding="utf-8")


def check_installed(models: list[str]) -> None:
    """Stop before a long run if a model is missing."""
    import httpx

    installed = {m["name"] for m in httpx.get(f"{config.OLLAMA_URL}/api/tags", timeout=30).json()["models"]}
    missing = [m for m in models if m not in installed and f"{m}:latest" not in installed]
    if missing:
        raise SystemExit(f"not installed in Ollama: {', '.join(missing)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--models", nargs="+", default=[])
    parser.add_argument("--judge-file", help="judge the answers saved earlier with --out, without re-running the models")
    parser.add_argument("--judge", default=config.JUDGE_MODEL, help='judge model, or "none"')
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--context", choices=["search", "all"], default="search", help='"all" gives the model every passage')
    parser.add_argument("--cases", default=str(Path(config.EVAL_DIR) / "answer_cases.json"))
    parser.add_argument("--out", help="write every answer to this JSON file")
    args = parser.parse_args()

    check_installed(args.models + ([] if args.judge == "none" else [args.judge, config.EMBEDDING_MODEL]))
    client = OllamaClient()
    if args.judge_file:
        check_installed([args.judge])
        results = json.loads(Path(args.judge_file).read_text(encoding="utf-8"))
        for rows in results.values():
            judge(client, args.judge, rows)
        save(args.judge_file, results)
        print(f"judge: {args.judge}\n")
        report(results)
        return

    cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    everything = None
    if args.context == "all":
        everything = [Hit(p.id, p.text, p.metadata, 0.0) for p in load_passages(config.SOP_DIR)]

    with tempfile.TemporaryDirectory() as chroma_path:
        # Search for every case first, so the embedding model and the answer model are not swapped per case.
        if everything is None:
            store = ChromaPassageStore(chroma_path, config.EMBEDDING_MODEL)
            build_index(store, config.EMBEDDING_MODEL)
            retrieved = [
                search(store, search_text(case["question"], case.get("vision")), args.top_k, config.EMBEDDING_MODEL)
                for case in cases
            ]
        else:
            retrieved = [everything] * len(cases)
    results = {model: run_model(client, model, cases, retrieved) for model in args.models}

    # Save before judging, so a judge failure cannot lose the answers.
    if args.out:
        save(args.out, results)
    if args.judge != "none":
        for rows in results.values():
            judge(client, args.judge, rows)

    context = "every passage" if everything else f"top {args.top_k} passages"
    print(f"{len(cases)} cases, context: {context}, judge: {args.judge}\n")
    report(results)
    if args.out:
        save(args.out, results)


if __name__ == "__main__":
    main()

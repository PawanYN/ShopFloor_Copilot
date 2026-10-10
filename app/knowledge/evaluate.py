"""Score retrieval for one or more embedding models on questions with a known answer passage.

    python -m app.knowledge.evaluate --models all-minilm nomic-embed-text mxbai-embed-large bge-m3
"""

import argparse
import json
import tempfile
import time
from pathlib import Path

from app import config
from app.knowledge.index import build_index
from app.knowledge.retrieval import search
from app.knowledge.store import ChromaPassageStore

CUTOFFS = (1, 3, 5)
KINDS = ("direct", "reworded", "exact_term")


def evaluate_model(model: str, questions: list[dict], chroma_path: str) -> dict:
    store = ChromaPassageStore(chroma_path, model)
    passages = build_index(store, model)
    search(store, "warm up", 1, model)  # load the model before timing

    hits = {kind: {cutoff: 0 for cutoff in CUTOFFS} for kind in KINDS}
    misses, started = [], time.perf_counter()
    for item in questions:
        found = [hit.id.split("/")[0] for hit in search(store, item["question"], max(CUTOFFS), model)]
        for cutoff in CUTOFFS:
            if set(found[:cutoff]) & set(item["expected"]):
                hits[item["kind"]][cutoff] += 1
        if not set(found) & set(item["expected"]):
            misses.append(f"{item['question']}  (wanted {item['expected'][0]}, got {found[:3]})")
    return {
        "model": model,
        "passages": passages,
        "hits": hits,
        "misses": misses,
        "ms_per_question": 1000 * (time.perf_counter() - started) / len(questions),
    }


def report(results: list[dict], questions: list[dict]) -> None:
    counts = {kind: sum(1 for q in questions if q["kind"] == kind) for kind in KINDS}
    total = len(questions)
    print(f"{total} questions ({', '.join(f'{counts[k]} {k}' for k in KINDS)}), {results[0]['passages']} passages\n")
    print(f"{'model':<20} " + " ".join(f"{'top-' + str(c):>7}" for c in CUTOFFS) + "   ms/question")
    for result in results:
        overall = [sum(result["hits"][kind][cutoff] for kind in KINDS) for cutoff in CUTOFFS]
        print(f"{result['model']:<20} " + " ".join(f"{n:>4}/{total}" for n in overall) + f"   {result['ms_per_question']:>8.0f}")

    for kind in KINDS:
        print(f"\n{kind} ({counts[kind]} questions)")
        for result in results:
            row = " ".join(f"{result['hits'][kind][cutoff]:>4}/{counts[kind]:<2}" for cutoff in CUTOFFS)
            print(f"  {result['model']:<18} {row}")

    for result in results:
        for miss in result["misses"]:
            print(f"\nmiss in top-{max(CUTOFFS)}  {result['model']}: {miss}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--models", nargs="+", required=True)
    parser.add_argument("--questions", default=str(Path(config.EVAL_DIR) / "retrieval_questions.json"))
    args = parser.parse_args()

    questions = json.loads(Path(args.questions).read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as chroma_path:
        results = [evaluate_model(model, questions, chroma_path) for model in args.models]
    report(results, questions)


if __name__ == "__main__":
    main()

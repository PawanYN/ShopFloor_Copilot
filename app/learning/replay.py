"""Show the learning loop at work, using results the real system produced.

Step 1, slow, needs the models: run every answer case once with each number of passages
and note whether the answer was right and how long it took.

    python -m app.learning.replay collect --model llama3.1

Step 2, fast, needs no model: replay those real results many times through the same
bandit the service uses, and print how its choice shifts.

    python -m app.learning.replay run --rounds 600 --time-scale 20
"""

import argparse
import json
import random
import tempfile
from collections import Counter
from pathlib import Path

from app import config
from app.learning.bandit import NO_IMAGE, Bandit, reward_for
from app.storage.sqlite import SqliteStore

OUTCOMES = Path(config.EVAL_DIR) / "replay_outcomes.json"


def collect(model: str) -> None:
    from app.knowledge.answer import answer_question, search_text
    from app.knowledge.evaluate_answers import mark
    from app.knowledge.index import build_index
    from app.knowledge.retrieval import search
    from app.knowledge.store import ChromaPassageStore
    from app.llm import OllamaClient

    cases = json.loads((Path(config.EVAL_DIR) / "answer_cases.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as chroma_path:
        store = ChromaPassageStore(chroma_path, config.EMBEDDING_MODEL)
        build_index(store, config.EMBEDDING_MODEL)
        # Search first for every case and setting, so the two models are not swapped on each call.
        retrieved = {
            (case["name"], top_k): search(store, search_text(case["question"], case.get("vision")), top_k, config.EMBEDDING_MODEL)
            for case in cases
            for top_k in config.TOP_K_CHOICES
        }

    client, outcomes = OllamaClient(), []
    for case in cases:
        vision = case.get("vision")
        for top_k in config.TOP_K_CHOICES:
            try:
                answer = answer_question(client, model, case["question"], retrieved[(case["name"], top_k)], vision)
                correct, seconds, decision = mark(case, answer)["correct"], answer.usage["seconds"], answer.decision
            except Exception as error:
                correct, seconds, decision = False, 0.0, f"error: {error}"[:80]
            outcomes.append(
                {
                    "case": case["name"],
                    "state": vision["defect_category"] if vision else NO_IMAGE,
                    "top_k": top_k,
                    "correct": correct,
                    "seconds": seconds,
                    "decision": decision,
                }
            )
            print(f"{case['name']} | top-{top_k} -> {decision}, {'right' if correct else 'wrong'}, {seconds}s", flush=True)
            OUTCOMES.write_text(json.dumps({"model": model, "outcomes": outcomes}, indent=1), encoding="utf-8")


def summarise(outcomes: list[dict]) -> None:
    print("What the real runs showed (share of right answers, average seconds):\n")
    print(f"| {'defect type':<22} | " + " | ".join(f"{'top-' + str(k):<16}" for k in config.TOP_K_CHOICES) + " |")
    print(f"|{'-' * 24}|" + "|".join("-" * 18 for _ in config.TOP_K_CHOICES) + "|")
    for state in sorted({o["state"] for o in outcomes}):
        cells = []
        for top_k in config.TOP_K_CHOICES:
            rows = [o for o in outcomes if o["state"] == state and o["top_k"] == top_k]
            right = sum(o["correct"] for o in rows)
            cells.append(f"{right}/{len(rows)} right, {sum(o['seconds'] for o in rows) / len(rows):.0f}s")
        print(f"| {state:<22} | " + " | ".join(f"{cell:<16}" for cell in cells) + " |")


def run(rounds: int, seed: int, time_scale: float, every: int) -> None:
    data = json.loads(OUTCOMES.read_text(encoding="utf-8"))
    outcomes = {(o["case"], o["top_k"]): o for o in data["outcomes"]}
    cases = sorted({(o["case"], o["state"]) for o in data["outcomes"]})
    states = sorted({state for _, state in cases})
    summarise(data["outcomes"])

    rng = random.Random(seed)
    with tempfile.TemporaryDirectory() as folder:
        bandit = Bandit(SqliteStore(str(Path(folder) / "replay.db")), config.TOP_K_CHOICES, config.EXPLORE_RATE, config.LEARNING_STEP, rng)
        print(
            f"\nReplay: {rounds} rounds, seed {seed}, answer model {data['model']}, explore rate {config.EXPLORE_RATE}, "
            f"step {config.LEARNING_STEP}, measured seconds divided by {time_scale:g}.\n"
            "Reward = (1 if the answer was right else 0) x 10 - seconds.\n"
        )
        print(f"| {'round':>5} | " + " | ".join(f"{state:<34}" for state in states) + " |")
        print(f"|{'-' * 7}|" + "|".join("-" * 36 for _ in states) + "|")
        picks: dict[str, list[int]] = {state: [] for state in states}
        for number in range(1, rounds + 1):
            case, state = rng.choice(cases)
            top_k, _ = bandit.choose(state)
            outcome = outcomes[(case, top_k)]
            bandit.update(state, top_k, reward_for(int(outcome["correct"]), outcome["seconds"] / time_scale))
            picks[state].append(top_k)
            if number % every == 0 or number == rounds:
                cells = []
                for state in states:
                    sheet = bandit.values(state)
                    scores = " ".join(f"k{k}={sheet[k]['value']:+.1f}" for k in config.TOP_K_CHOICES)
                    cells.append(f"best top-{bandit.best(state)} ({scores})")
                print(f"| {number:>5} | " + " | ".join(f"{cell:<34}" for cell in cells) + " |")

        print("\nHow often each setting was used, first 30 and last 30 questions of each defect type:\n")
        for state in states:
            first, last = Counter(picks[state][:30]), Counter(picks[state][-30:])
            show = lambda count: ", ".join(f"top-{k}: {count.get(k, 0)}" for k in config.TOP_K_CHOICES)
            print(f"- {state}: first 30 -> {show(first)}; last 30 -> {show(last)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    collecting = commands.add_parser("collect")
    collecting.add_argument("--model", default=config.ANSWER_MODEL)
    running = commands.add_parser("run")
    running.add_argument("--rounds", type=int, default=600)
    running.add_argument("--seed", type=int, default=7)
    running.add_argument("--every", type=int, default=50)
    running.add_argument("--time-scale", type=float, default=1.0, help="divide the measured seconds by this, to stand in for faster hardware")
    args = parser.parse_args()
    if args.command == "collect":
        collect(args.model)
    else:
        run(args.rounds, args.seed, args.time_scale, args.every)


if __name__ == "__main__":
    main()

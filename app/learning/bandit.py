"""Epsilon-greedy contextual bandit: learns the best number of SOP passages for each defect type.

State   the defect category the camera found, or "no_image"
Action  how many passages to give the model (RAG top-K)
Reward  (feedback score x 10) - (latency in seconds)
"""

import random

NO_IMAGE = "no_image"
BEST_KNOWN = "best_known"
TRYING_ANOTHER = "trying_another"


def reward_for(score: int, latency_seconds: float) -> float:
    return score * 10 - latency_seconds


class Bandit:
    def __init__(self, store, actions: tuple[int, ...], epsilon: float, step: float, rng: random.Random | None = None) -> None:
        self.store = store
        self.actions = actions
        self.epsilon = epsilon
        self.step = step
        self.rng = rng or random.Random()

    def values(self, state: str) -> dict[int, dict]:
        """The score sheet for one state: {action: {"value": ..., "count": ...}}."""
        saved = self.store.learning_values(state)
        return {action: saved.get(action, {"value": 0.0, "count": 0}) for action in self.actions}

    def best(self, state: str) -> int:
        sheet = self.values(state)
        # A setting never tried comes first, so each one is tried before any is trusted.
        untried = [action for action in self.actions if sheet[action]["count"] == 0]
        if untried:
            return untried[0]
        return max(self.actions, key=lambda action: sheet[action]["value"])

    def choose(self, state: str) -> tuple[int, str]:
        """Usually the best known setting; about epsilon of the time, one of the others."""
        best = self.best(state)
        if len(self.actions) > 1 and self.rng.random() < self.epsilon:
            return self.rng.choice([action for action in self.actions if action != best]), TRYING_ANOTHER
        return best, BEST_KNOWN

    def update(self, state: str, action: int, reward: float, transaction_id: str | None = None) -> float:
        """Move the score a fixed step toward the new reward, so recent results count more."""
        current = self.values(state)[action]
        if current["count"] == 0:
            value = reward
        else:
            value = current["value"] + self.step * (reward - current["value"])
        self.store.save_learning_update(state, action, reward, value, current["count"] + 1, transaction_id)
        return value

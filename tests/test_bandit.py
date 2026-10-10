import random

from app.learning.bandit import BEST_KNOWN, TRYING_ANOTHER, Bandit, reward_for
from app.storage.sqlite import SqliteStore


def bandit(tmp_path, epsilon=0.0, step=0.5) -> Bandit:
    return Bandit(SqliteStore(str(tmp_path / "learn.db")), (1, 3, 5), epsilon, step, random.Random(7))


def test_reward_is_score_times_ten_minus_latency():
    assert reward_for(1, 4.0) == 6.0
    assert reward_for(0, 4.0) == -4.0


def test_every_setting_is_tried_before_the_best_is_used(tmp_path):
    learner = bandit(tmp_path)
    for reward in (2.0, 6.0, 4.0):
        action, choice = learner.choose("crack")
        assert choice == BEST_KNOWN
        learner.update("crack", action, reward)
    assert learner.best("crack") == 3


def test_recent_results_count_more_and_the_choice_shifts(tmp_path):
    learner = bandit(tmp_path, step=0.5)
    for action, reward in ((1, 2.0), (3, 6.0), (5, 4.0)):
        learner.update("crack", action, reward)

    # 3 passages starts as the best, then keeps getting poor results.
    assert learner.update("crack", 3, 0.0) == 3.0
    assert learner.update("crack", 3, 0.0) == 1.5
    assert learner.best("crack") == 5


def test_states_are_learned_separately_and_survive_a_restart(tmp_path):
    learner = bandit(tmp_path)
    learner.update("crack", 5, 8.0, "t1")
    learner.update("no_image", 1, 9.0, "t2")

    again = bandit(tmp_path)
    assert again.values("crack")[5] == {"value": 8.0, "count": 1}
    assert again.values("no_image")[5]["count"] == 0
    assert [(row["state"], row["action"], row["reward"]) for row in again.store.learning_history()] == [
        ("crack", 5, 8.0),
        ("no_image", 1, 9.0),
    ]


def test_about_one_choice_in_ten_tries_another_setting(tmp_path):
    learner = bandit(tmp_path, epsilon=0.1)
    for action, reward in ((1, 2.0), (3, 6.0), (5, 4.0)):
        learner.update("crack", action, reward)

    choices = [learner.choose("crack") for _ in range(1000)]
    tries = [action for action, choice in choices if choice == TRYING_ANOTHER]
    assert 60 < len(tries) < 140
    assert all(action != 3 for action in tries)
    assert all(action == 3 for action, choice in choices if choice == BEST_KNOWN)

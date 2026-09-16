from itertools import permutations
from random import Random

from web_backend.reference_fact_matching import minimum_rank_matching


def test_matching_reassigns_early_choice_to_cover_both_references():
    edges = [((0,), 0, 0), ((1,), 0, 1), ((1,), 1, 0)]
    assert minimum_rank_matching(2, 2, edges) == {0: 1, 1: 0}


def test_higher_priority_identity_wins_over_all_lower_priority_state_costs():
    edges = [((0, 1), 0, 0), ((1, 0), 0, 1), ((1, 0), 1, 0), ((0, 1), 1, 1)]
    assert minimum_rank_matching(2, 2, edges) == {0: 0, 1: 1}


def test_matching_matches_exhaustive_small_assignment_cost():
    random = Random(17)
    for _ in range(20):
        costs = [[random.randrange(8) for _ in range(4)] for _ in range(3)]
        edges = [((costs[row][col],), row, col) for row in range(3) for col in range(4)]
        pairs = minimum_rank_matching(3, 4, edges)
        optimum = min(
            sum(costs[row][col] for row, col in enumerate(columns))
            for columns in permutations(range(4), 3)
        )
        assert sum(costs[row][col] for row, col in pairs.items()) == optimum


def test_missing_edge_never_matches_an_unrelated_fact():
    assert minimum_rank_matching(2, 1, [((0,), 0, 0)]) == {0: 0}

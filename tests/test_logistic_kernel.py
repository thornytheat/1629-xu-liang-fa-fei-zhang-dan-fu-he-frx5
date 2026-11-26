from math import isfinite

from peakledger.penalty_logit.estimator import objective, probability


def test_extreme_tariff_odds_never_overflow_or_invert():
    assert 0 <= probability(-900) < probability(0) < probability(900) <= 1
    assert probability(0) == 0.5
    assert isfinite(objective([(1, 1), (1, -1)], [0, 1], (0.4, 800)))

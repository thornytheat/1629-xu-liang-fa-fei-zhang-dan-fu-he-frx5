from copy import deepcopy

import pytest

from peakledger.charge_notices.service import known_labels, sample, stage
from peakledger.tariff_signature.service import encode, learn_bank
from peakledger.penalty_logit.service import fit
from peakledger.billing_holdout.service import split
from peakledger.engine import ROOT, plan
from peakledger.settings import DEFAULT_DAY, FIELD_BOUNDS, GROUPS


@pytest.fixture(scope="session")
def original():
    return sample(ROOT)


@pytest.fixture
def packet(original):
    return deepcopy(original)


@pytest.fixture
def observation():
    return {
        "case_id": "QA-HD",
        "group": GROUPS[0],
        "day": 22,
        "arrived": 22,
        "revision": 1,
        "clock": 32,
        "measurements": {
            key: (0 if (lo, hi) == (0, 1) else (lo + hi) / 2)
            for key, (lo, hi) in FIELD_BOUNDS.items()
        },
    }


@pytest.fixture(scope="session")
def learning(original):
    book = stage(original, DEFAULT_DAY)
    boundary = split(DEFAULT_DAY)
    historical = stage(original, boundary.train_before - 1)
    bank = learn_bank(historical.observations, boundary.train_before)
    signals = [encode(row, bank) for row in book.observations]
    history = [encode(row, bank) for row in historical.observations]
    model = fit(history, known_labels(historical, boundary.train_before - 1))
    return book, boundary, bank, signals, history, model


@pytest.fixture(scope="session")
def report(original):
    return plan(original)

from math import exp, fsum, log, log1p

from .linear_math import dot


def _bill_row(s):
    over, gap, meter, fee = s.normalized
    return (1.0, over, gap, meter, fee, max(0.0, over) * max(0.0, meter) * 0.45)


def probability(link):
    if link < 0:
        term = exp(max(-700.0, link))
        return term / (1 + term)
    return 1 / (1 + exp(-min(700.0, link)))


def objective(bills, labels, weights):
    total = 0.0
    for row, label in zip(bills, labels):
        link = dot(row, weights)
        total += max(0.0, link) - label * link + log1p(exp(-abs(link)))
    return total / len(bills) + 0.026 * dot(weights[1:], weights[1:]) / 2


def train(rows):
    bills = [_bill_row(row.signal) for row in rows]
    labels = [row.y for row in rows]
    base = (fsum(labels) + 0.5) / (len(labels) + 1)
    weights = (log(base / (1 - base)), 0.0, 0.0, 0.0, 0.0, 0.0)
    loss = objective(bills, labels, weights)
    for _ in range(180):
        residuals = [
            probability(dot(row, weights)) - label for row, label in zip(bills, labels)
        ]
        grad = tuple(
            fsum(a * b for a, b in zip(column, residuals)) / len(bills)
            + (0.026 * weights[i] if i else 0)
            for i, column in enumerate(zip(*bills))
        )
        if max(abs(g) for g in grad) < 1e-6:
            break
        rate = 1.0
        while rate >= 0.007:
            candidate = tuple(w - rate * g for w, g in zip(weights, grad))
            trial = objective(bills, labels, candidate)
            if trial <= loss:
                break
            rate /= 2
        if rate < 0.007 or loss - trial < 1e-8:
            break
        weights, loss = candidate, trial
    return {
        "billing_odds": weights,
        "log_loss": loss,
        "wire_variance_penalty": 0.026,
        "prior_disputes": base,
    }


def infer(state, signal):
    return probability(dot(_bill_row(signal), state["billing_odds"]))


def explain(state):
    return state

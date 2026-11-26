from decimal import Decimal, ROUND_HALF_EVEN
from statistics import median


def _balance(document):
    d = document.record.reported
    if (
        d["observed_kw"] is None
        or d["subscribed_kw"] is None
        or d["multiplicity"] is None
    ):
        return None
    corrected = Decimal(str(d["observed_kw"])) * Decimal(str(d["multiplicity"]))
    return float(
        (corrected - Decimal(str(d["subscribed_kw"]))).quantize(
            Decimal(".01"), rounding=ROUND_HALF_EVEN
        )
    )


def context(current, neighbors, old, score):
    contract = current.record.reported
    corrected = _balance(current)
    eligible = [
        (balance, record.record.reported["fee"])
        for record in old
        if record.record.reported["amendment"] == 1
        and (balance := _balance(record)) is not None
        and balance > 5
        and record.record.reported["fee"] is not None
    ]
    unit_rate = (
        median(fee / balance for balance, fee in eligible)
        if len(eligible) >= 10
        else None
    )
    estimator = (
        round(unit_rate * max(0, corrected), 2)
        if corrected is not None and unit_rate
        else None
    )
    book = contract["fee"]
    dispute = Decimal(str(book or 0)) * Decimal(str(score))
    apparent = estimator is not None and book and estimator * 2.6 < book
    return {
        "decision": "计量修正后罚费差额过大，移交人工查表"
        if apparent and (contract["gap_min"] or 0) > 19
        else "",
        "support": len(eligible),
        "corrected_margin_kw": corrected,
        "reference_fee_yuan": estimator,
        "dispute_value_yuan": float(dispute.quantize(Decimal(".01"))),
    }

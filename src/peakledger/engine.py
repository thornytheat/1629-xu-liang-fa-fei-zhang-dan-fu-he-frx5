from pathlib import Path

from .charge_notices.service import known_labels, sample, stage
from .tariff_signature.service import (
    encode,
    fit_audit,
    learn_bank,
    measure_sensitivity,
    ranges,
    reference_summary,
    trace,
)
from .penalty_logit.service import fit, forecast_card
from .billing_holdout.service import backcheck, score_card, split
from .meter_regimes.service import decide, readiness, review, shift_alerts
from .review_exposure.confirmation import Option, impact_cents, maximin, totals_for
from .review_exposure.domain import resource_limit
from .review_exposure.local_context import context
from .review_exposure.operations import operational_check
from .review_exposure.service import (
    allocate,
    allocate_requests,
    project_requests,
    quota,
    review_capacity,
    summarize_workload,
)
from .invoice_reconcile.service import compile_delivery
from .settings import DEFAULT_BUDGET, DEFAULT_DAY, FIELD_BOUNDS, CRITICAL_FIELDS
from dataclasses import replace

ROOT = Path(__file__).resolve().parents[2]


def _filled(record):
    fields = record.reported
    return {
        key: (max(lo, 0.0) if key in CRITICAL_FIELDS else (lo + hi) / 2)
        if fields.get(key) is None
        else fields[key]
        for key, (lo, hi) in FIELD_BOUNDS.items()
    }


def _pending_gears(intake):
    """只保留确实有两档待确认系数的计量组。"""
    grouped = {}
    for entry in intake.coefficients:
        grouped.setdefault(entry.group, set()).add(entry.coefficient)
    return {
        group: tuple(sorted(values))
        for group, values in grouped.items()
        if len(values) == 2
    }


def _with_gear(signal, coefficient, bank):
    reported = {**signal.record.reported, "multiplicity": coefficient}
    return encode(replace(signal.record, reported=reported), bank)


def _assess(signal, *, model, assessment, shifts, history, current, historic):
    """按现有复核条件评判一张账单；返回 (gate, card, operating, local)。"""
    rules = decide(signal, shifts, assessment.test_passed, history)
    card = score_card(model, assessment, signal)
    operative = card.estimate if rules.allowed else card.prior
    filled = _filled(signal.record)
    operating = operational_check(filled, operative)
    local = context(
        signal,
        current[signal.record.group],
        historic.get(signal.record.group, []),
        operative,
    )
    if rules.allowed and (operating["requires_operator"] or local["decision"]):
        reasons = tuple(
            note for note in (operating["reason"], local["decision"]) if note
        )
        rules = replace(rules, allowed=False, reasons=reasons, source="incumbent")
    return rules, card, operating, local


def plan(packet=None, *, as_of=DEFAULT_DAY, capacity=DEFAULT_BUDGET):
    if type(as_of) is not int or not 70 <= as_of <= 36_500:
        raise ValueError("快照日上午必须在第 70 日至第 36500 日之间")
    capacity = quota(capacity)
    packet = sample(ROOT) if packet is None else packet
    intake = stage(packet, as_of)
    bounds = split(as_of)
    training_snapshot = stage(packet, bounds.train_before - 1)
    bank = learn_bank(training_snapshot.observations, bounds.train_before)
    signals = [encode(row, bank) for row in intake.observations]
    history = [encode(row, bank) for row in training_snapshot.observations]
    model = fit(history, known_labels(training_snapshot, bounds.train_before - 1))
    assessment = backcheck(signals, intake, bounds, model)
    # 候选只用在快照日已入账的单据，候选结果标签不参与得分。
    ready = [
        item for item in signals if bounds.validate_before <= item.record.day <= as_of
    ]
    shifts = review(history, ready)
    current_groups = {}
    historic_groups = {}
    for row in ready:
        current_groups.setdefault(row.record.group, []).append(row)
    for row in history:
        historic_groups.setdefault(row.record.group, []).append(row)

    gears = _pending_gears(intake)
    details = {}
    pairings = {}
    audits = {}
    variants = {}
    for signal in ready:
        group = signal.record.group
        case_id = signal.record.case_id
        gate, card, operating, local = _assess(
            signal,
            model=model,
            assessment=assessment,
            shifts=shifts,
            history=history,
            current=current_groups,
            historic=historic_groups,
        )
        details[case_id] = {
            **trace(signal),
            "trained_estimate": card.estimate,
            "incumbent_estimate": card.prior,
            "trust_reasons": list(gate.reasons),
            "used_source": gate.source,
            "operational_check": operating,
            "operating_context": local,
            "sensitivity": measure_sensitivity(signal, bank, ("fee", "subscribed_kw")),
        }
        pairings[case_id] = (card, gate)
        if group not in gears:
            continue
        options = []
        for coefficient in gears[group]:
            sampled = _with_gear(signal, coefficient, bank)
            options.append(
                (coefficient,)
                + _assess(
                    sampled,
                    model=model,
                    assessment=assessment,
                    shifts=shifts,
                    history=history,
                    current=current_groups,
                    historic=historic_groups,
                )
            )
        variants[case_id] = tuple(options)
        audits[case_id] = {
            "group": group,
            "options": list(gears[group]),
            "estimates": [
                {
                    "coefficient": coefficient,
                    "estimate": card.estimate,
                    "prior": card.prior,
                    "allowed": gate.allowed,
                    "reasons": list(gate.reasons),
                }
                for coefficient, gate, card, _, _ in options
            ],
        }
        if all(gate.allowed for _, gate, _, _, _ in options):
            # 两档都符合现有复核条件：取较低概率作为当班口径，席位由名单统一决定。
            conservative = min(
                (card for _, _, card, _, _ in options),
                key=lambda entry: entry.estimate,
            )
            pairings[case_id] = (
                replace(card, estimate=conservative.estimate),
                replace(gate, allowed=True, reasons=(), source="trained"),
            )
            details[case_id]["trust_reasons"] = []
            details[case_id]["used_source"] = "trained"
        else:
            # 任一档不符合现有复核条件：这张账单不占席位。
            reasons = tuple(
                dict.fromkeys(
                    note for _, gate, _, _, _ in options for note in gate.reasons
                )
            )
            pairings[case_id] = (
                replace(card, estimate=card.prior),
                replace(gate, allowed=False, reasons=reasons, source="incumbent"),
            )
        details[case_id]["pending_gears"] = audits[case_id]

    order = [signal.record.case_id for signal in ready]
    roster, confirmation = _lock_roster(
        ready, pairings, variants, audits, gears, capacity, as_of
    )
    result = allocate(
        [pairings[case_id] for case_id in order], capacity, as_of, roster=roster
    )
    return compile_delivery(
        snapshot=as_of,
        plan=result,
        intake=intake,
        assessment=assessment,
        drift=shifts,
        model=forecast_card(model, ready, bank),
        signals={
            "ranges": ranges(ready),
            "reference_coverage": fit_audit(ready, bank),
            "reference_scale": reference_summary(bank),
            "shift_alerts": shift_alerts(shifts),
            "shift_coverage": readiness(shifts),
            "workload_review": summarize_workload(result.decisions, details),
            "capacity_review": review_capacity(result),
        },
        details=details,
        confirmation=confirmation,
    )


def _scenario_pairs(ready, pairings, variants, index):
    pairs = []
    for signal in ready:
        case_id = signal.record.case_id
        options = variants.get(case_id)
        if options is None:
            pairs.append(pairings[case_id])
        else:
            _, gate, card, _, _ = options[min(index, len(options) - 1)]
            pairs.append((card, gate))
    return pairs


def _lock_roster(ready, pairings, variants, audits, gears, capacity, as_of):
    """各档各自排序；名单不同时锁定 maximin 名单。"""
    if not variants:
        return None, None
    width = max(len(options) for options in variants.values())
    queues = [
        project_requests(_scenario_pairs(ready, pairings, variants, index), as_of)
        for index in range(width)
    ]
    scenarios = []
    for queue in queues:
        outcome = allocate_requests(queue, capacity)
        scenarios.append(
            tuple(
                sorted(
                    row.case_id
                    for row in outcome.decisions
                    if row.status == "allocated"
                )
            )
        )
    agreed = all(item == scenarios[0] for item in scenarios)
    options = _options(queues, ready)
    if agreed:
        roster = scenarios[0]
        totals = totals_for(roster, options)
    else:
        roster, totals = maximin(options, capacity, resource_limit(capacity))
    active = {audits[case_id]["group"] for case_id in audits}
    return roster, {
        "pending": {
            group: list(values)
            for group, values in sorted(gears.items())
            if group in active
        },
        "audits": {case_id: audits[case_id] for case_id in sorted(audits)},
        "scenarios": [list(item) for item in scenarios],
        "agreed": agreed,
        "roster": list(roster),
        "totals_cents": list(totals),
        "critical_cents": min(totals) if totals else 0,
    }


def _options(queues, ready):
    """各档都是候选的账单才可能占席位；记下每档的精确期望罚费。"""
    records = {signal.record.case_id: signal.record for signal in ready}
    tables = [{row.case_id: row for row in queue} for queue in queues]
    common = set(tables[0])
    for table in tables[1:]:
        common &= set(table)
    options = []
    for case_id in sorted(common):
        rows = [table[case_id] for table in tables]
        if any(row.status != "candidate" for row in rows):
            continue
        filled = _filled(records[case_id])
        options.append(
            Option(
                case_id,
                rows[0].resource,
                rows[0].units,
                tuple(
                    impact_cents(filled["fee"], filled["gap_min"], row.estimate)
                    for row in rows
                ),
            )
        )
    return options

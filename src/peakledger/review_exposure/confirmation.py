"""换档待确认系数的两档重估与稳健名单选择。

某计量组换档后可能留下两个待确认的互感器校验系数（档位）。整组最终只会
采用其中一档，因此在锁定当班名单之前要用各档分别重估争议概率：

* 一张账单只有在**每一档**下都符合现有复核条件时才可能占用席位；
* 各档各自选出的名单不同时，当班仍只锁一份名单，取各档中较低的预期争议
  罚费总额尽可能高的那一份（maximin）；
* 金额累计统一换算成整数分（``Decimal``，四舍六入五成双），取舍全程只比较
  整数，避免浮点舍入误差改变结果；
* 席位总额与组内上限沿用现有额度。
"""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_EVEN

CENT = Decimal("0.01")
ONE = Decimal("1")
FORTY = Decimal("40")


def impact_cents(fee, gap_min, estimate) -> int:
    """把期望争议罚费换算成整数分，作为无歧义的比较单位。

    口径与 ``review_exposure.operations.operational_check`` 的 ``impact``
    相同：``fee * estimate * (1 + gap_min / 40)``。整数分让累计总额的
    比较不受浮点舍入影响。
    """
    value = (
        Decimal(str(fee))
        * Decimal(str(estimate))
        * (ONE + Decimal(str(gap_min)) / FORTY)
    )
    return int((value / CENT).quantize(Decimal("1"), rounding=ROUND_HALF_EVEN))


@dataclass(frozen=True)
class Option:
    """一张可复核账单在每种档位下的精确期望罚费（整数分）。"""

    case_id: str
    resource: str
    units: int
    impacts: tuple[int, ...]


def _prune(entries):
    """按各档累计金额去支配并去重。

    ``entries`` 为 ``(cost, totals, ids)``。后续只能继续叠加相同选项，因此
    若一项的占位不高于、且各档累计都不低于另一项，则另一项在任何最大化
    目标下都不可能胜出，可以安全删除。当占位与各档金额都相同时，保留
    字典序更小的一份以得到确定结果。
    """
    unique = {}
    for cost, totals, ids in entries:
        key = (cost, totals)
        current = unique.get(key)
        if current is None or tuple(sorted(ids)) < tuple(sorted(current)):
            unique[key] = ids
    items = [
        (cost, totals, ids) for (cost, totals), ids in unique.items()
    ]
    kept = []
    for cost, totals, ids in items:
        dominated = False
        for other_cost, other_totals, other_ids in items:
            if (other_cost, other_totals) == (cost, totals):
                continue
            if other_cost <= cost and all(
                a >= b for a, b in zip(other_totals, totals)
            ) and (
                other_cost < cost
                or any(a > b for a, b in zip(other_totals, totals))
            ):
                dominated = True
                break
        if not dominated:
            kept.append((cost, totals, ids))
    return kept


def _group_frontier(rows, cap, width):
    """组内按席位数背包，返回各占用量的 Pareto 前沿。"""
    states = {0: [((0,) * width, ())]}
    for option in sorted(rows, key=lambda row: row.case_id):
        updated = {cost: list(entries) for cost, entries in states.items()}
        for cost, entries in states.items():
            new_cost = cost + option.units
            if new_cost > cap:
                continue
            bucket = updated.setdefault(new_cost, [])
            for totals, ids in entries:
                bucket.append(
                    (
                        tuple(a + b for a, b in zip(totals, option.impacts)),
                        (*ids, option.case_id),
                    )
                )
        states = {
            cost: [
                (totals, ids)
                for _, totals, ids in _prune(
                    [(cost, totals, ids) for totals, ids in entries]
                )
            ]
            for cost, entries in updated.items()
        }
    return [
        (cost, totals, ids)
        for cost, entries in states.items()
        for totals, ids in entries
    ]


def _select(frontier):
    best = None
    for cost, totals, ids in frontier:
        key = (min(totals), sum(totals), -cost, tuple(sorted(ids)))
        if best is None or key > best[0]:
            best = (key, totals, ids)
    return best


def maximin(options, capacity, group_cap):
    """在席位额度内选出使各档较低总额最大的名单。

    返回 ``(case_ids, totals)``，``totals`` 为每种档位的整数分合计。
    """
    if not options:
        return (), ()
    width = len(options[0].impacts)
    grouped = {}
    for option in options:
        grouped.setdefault(option.resource, []).append(option)
    frontier = [(0, (0,) * width, ())]
    for _, rows in sorted(grouped.items()):
        local = _group_frontier(rows, min(capacity, group_cap), width)
        merged = []
        for used, totals, ids in frontier:
            for cost, values, claimed in local:
                if used + cost > capacity:
                    continue
                merged.append(
                    (
                        used + cost,
                        tuple(a + b for a, b in zip(totals, values)),
                        (*ids, *claimed),
                    )
                )
        frontier = _prune(merged)
    best = _select(frontier)
    if best is None:
        return (), (0,) * width
    return tuple(sorted(best[2])), best[1]


def gear_total(roster, options, index):
    chosen = set(roster)
    return sum(
        option.impacts[index] for option in options if option.case_id in chosen
    )


def totals_for(roster, options):
    if not options:
        return ()
    return tuple(
        gear_total(roster, options, index)
        for index in range(len(options[0].impacts))
    )

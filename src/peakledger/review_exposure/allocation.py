from collections import defaultdict


def _better(candidate, previous):
    if previous is None:
        return True
    if abs(candidate[0] - previous[0]) > 1e-8:
        return candidate[0] > previous[0]
    return candidate[1] < previous[1]


def _picks(rows, ceiling):
    dp = {0: (0.0, ())}
    for row in rows:
        for cost, (value, matched) in list(dp.items()):
            new_cost = cost + row.units
            if new_cost > ceiling:
                continue
            offer = (value + row.priority, tuple(sorted((*matched, row.case_id))))
            if _better(offer, dp.get(new_cost)):
                dp[new_cost] = offer
    return dp


def reservations(candidates, remaining, resource_cap):
    buckets = defaultdict(list)
    for row in candidates:
        buckets[row.resource].append(row)
    budget = {0: (0.0, ())}
    for resource, rows in sorted(buckets.items()):
        merged = {}
        local = _picks(rows, min(remaining, resource_cap))
        for used, (value, claimed) in budget.items():
            for cost, (new_value, new_claimed) in local.items():
                if used + cost <= remaining:
                    option = (value + new_value, tuple(sorted(claimed + new_claimed)))
                    if _better(option, merged.get(used + cost)):
                        merged[used + cost] = option
        budget = merged
    _, (_, match) = min(
        budget.items(), key=lambda item: (-item[1][0], item[0], item[1][1])
    )
    reasons = {
        row.case_id: "RESOURCE_CEILING"
        if row.units > resource_cap
        else "PORTFOLIO_CAPACITY"
        for row in candidates
        if row.case_id not in match
    }
    return set(match), reasons

from collections import defaultdict
from math import isfinite

REVIEW_NAME = "账期未复核风险"
IMPACT_NAME = "期望争议罚费/元"
HEADROOM_NAME = "签约电力余量/kW"
OVERRIDE_NOTE = "互感器记录缺失过多，移交计量核验"


def operational_check(readings, estimate):
    """争议概率按罚费金额和采样间隙转换成优先级。费率生效是独立前置条件。"""
    observed_kw = readings["observed_kw"]
    subscribed_kw = readings["subscribed_kw"]
    gap_min = readings["gap_min"]
    multiplicity = readings["multiplicity"]
    fee = readings["fee"]
    amendment = readings["amendment"]
    impact = fee * estimate * (1 + gap_min / 40)
    headroom = subscribed_kw - observed_kw * multiplicity
    override = bool(amendment >= 1 and gap_min > 24 and abs(1 - multiplicity) > 0.22)
    if not isfinite(impact) or not isfinite(headroom):
        raise ValueError("业务复核的观测量超出计算范围")
    return {
        "name": REVIEW_NAME,
        "impact_label": IMPACT_NAME,
        "headroom_label": HEADROOM_NAME,
        "impact": round(impact, 6),
        "headroom": round(headroom, 6),
        "requires_operator": override,
        "reason": OVERRIDE_NOTE if override else "",
    }


def summarize_workload(actions, evidence):
    distribution = defaultdict(
        lambda: {
            "selected_impact": 0.0,
            "selected": 0,
            "tight_window": 0,
            "needs_operator": 0,
        }
    )
    for action in actions:
        branch = distribution[action.cohort]
        current = evidence[action.case_id]["operational_check"]
        if action.status == "allocated":
            branch["selected"] += 1
            branch["selected_impact"] += current["impact"]
            if current["headroom"] < 0:
                branch["tight_window"] += 1
        if current["requires_operator"]:
            branch["needs_operator"] += 1
    return {
        name: {**data, "selected_impact": round(data["selected_impact"], 4)}
        for name, data in sorted(distribution.items())
    }

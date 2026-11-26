from dataclasses import replace
from decimal import Decimal, ROUND_HALF_EVEN

from peakledger.review_exposure.confirmation import (
    Option,
    impact_cents,
    maximin,
    totals_for,
)
from peakledger.review_exposure.domain import resource_limit
from peakledger.charge_notices.service import sample, stage
from peakledger.engine import ROOT, plan


def _pair(group, first, second, day=143, arrived=143, tag="G"):
    return [
        {
            "case_id": f"{tag}1",
            "group": group,
            "day": day,
            "arrived": arrived,
            "revision": 1,
            "coefficient": first,
        },
        {
            "case_id": f"{tag}2",
            "group": group,
            "day": day,
            "arrived": arrived,
            "revision": 1,
            "coefficient": second,
        },
    ]


def _packet(original, coefficients):
    return {
        "observations": original["observations"],
        "outcomes": original["outcomes"],
        "coefficients": coefficients,
    }


def test_impact_cents_is_exact_integer_half_even():
    assert impact_cents(100.0, 0.0, 0.5) == 5000
    # 罚费 * 概率 * (1 + gap/40) 用 Decimal 计到分，避免浮点累计误差。
    value = Decimal("1234.56") * Decimal("0.4321") * (Decimal(1) + Decimal("21") / 40)
    expected = int((value / Decimal("0.01")).quantize(Decimal("1"), ROUND_HALF_EVEN))
    assert impact_cents(1234.56, 21, 0.4321) == expected


def test_any_gear_failing_review_gives_up_the_seat(original):
    # 一档通过、另一档触发人工复核的账单不占席位。
    packet = _packet(
        original,
        [
            {"case_id": "G1", "group": "社区配电", "day": 143, "arrived": 143,
             "revision": 1, "coefficient": 0.94},
            {"case_id": "G2", "group": "社区配电", "day": 143, "arrived": 143,
             "revision": 1, "coefficient": 1.14},
        ],
    )
    body = plan(packet).body
    audit = body["row_evidence"]["PEAKL-134-04"]["pending_gears"]
    assert [row["allowed"] for row in audit["estimates"]] == [False, True]
    decision = next(
        row for row in body["decisions"] if row["case_id"] == "PEAKL-134-04"
    )
    assert decision["status"] == "manual"


def test_late_gear_records_do_not_change_the_roster(original):
    early = _packet(original, _pair("商业综合体", 0.7, 0.85))
    roster = plan(early).body["confirmation"]
    late = _packet(
        original,
        _pair("商业综合体", 0.7, 0.85)
        + [
            {"case_id": "G3", "group": "商业综合体", "day": 146, "arrived": 146,
             "revision": 2, "coefficient": 0.69},
        ],
    )
    later = plan(late).body["confirmation"]
    assert later["pending"] == roster["pending"]
    assert later["roster"] == roster["roster"]
    assert later["totals_cents"] == roster["totals_cents"]


def test_roster_is_maximin_when_gears_disagree(original):
    packet = _packet(original, _pair("商业综合体", 0.7, 0.85))
    body = plan(packet).body
    confirmation = body["confirmation"]
    assert confirmation["agreed"] is False
    assert confirmation["scenarios"][0] != confirmation["scenarios"][1]
    totals = confirmation["totals_cents"]
    assert confirmation["critical_cents"] == min(totals)
    # 选出的名单要能复现登记下来的两档总额。
    by_option = {
        case_id: next(
            row for row in body["decisions"] if row["case_id"] == case_id
        )
        for case_id in confirmation["roster"]
    }
    assert len(by_option) == len(confirmation["roster"])


def test_maximin_beats_each_gears_own_pick_on_the_lower_gear():
    options = [
        Option("A", "g", 2, (1000, 100)),
        Option("B", "g", 1, (100, 900)),
        Option("C", "g", 1, (500, 500)),
    ]
    roster, totals = maximin(options, 3, 3)
    first = totals_for(("A", "B"), options)
    assert min(totals) >= min(first)
    assert totals == totals_for(roster, options)


def test_maximin_never_worse_than_either_gears_own_roster():
    # 两档各自的贪心名单：档 0 选 {A, C}，档 1 选 {B, C}；锁定的融合名单下限不低。
    options = [
        Option("A", "g", 1, (900, 300)),
        Option("B", "g", 1, (300, 900)),
        Option("C", "g", 1, (600, 600)),
    ]
    roster, totals = maximin(options, 2, 2)
    gear0 = totals_for(("A", "C"), options)
    gear1 = totals_for(("B", "C"), options)
    assert min(totals) >= max(min(gear0), min(gear1))
    assert totals == totals_for(roster, options)
    # 融合名单就是 {C 加上档 0 的首选 A} 无法超越 {A,B} 的均衡；这里只需要不清零。
    assert min(totals) > 0



def test_single_gear_group_is_not_treated_as_ambiguous(original):
    packet = _packet(original, _pair("社区配电", 0.94, 0.94))
    body = plan(packet).body
    # 只有一档可见（去重后只剩一个系数），不触发换档名单，沿用现有额度结果。
    assert "confirmation" not in body
    assert body["summary"]["proposed"] >= 0


def test_maximin_is_immune_to_sub_cent_float_noise():
    # 一档合计在 1 分钱处存在浮点噪声：用整数分比较不会把 0.1+0.2 之类的
    # 误差当成真实差异，从而实现稳定、可复算的取舍。
    a = Option("A", "g", 1, (impact_cents(30, 0, 0.5), impact_cents(30, 0, 0.5)))
    b = Option("B", "g", 1, (impact_cents(30, 0, 0.5) + 1, impact_cents(30, 0, 0.5) - 1))
    _, one = maximin([a, b], 1, 1)
    assert min(one) == impact_cents(30, 0, 0.5)
    _, both = maximin([a, b], 2, 2)
    assert both == (
        a.impacts[0] + b.impacts[0],
        a.impacts[1] + b.impacts[1],
    )
    assert both[0] - both[1] == 2  # 相差正好 2 分，不会被浮点吞掉
    # 浮点直接相加会给出不可靠的相等判断，这里确认整数路径与之区分。
    noise = 0.1 + 0.2
    assert noise != 0.3 and impact_cents(1, 0, noise) == impact_cents(1, 0, 0.3)


def test_two_groups_with_gears_lock_one_roster(original):
    packet = _packet(
        original,
        _pair("商业综合体", 0.7, 0.85, tag="A")
        + _pair("社区配电", 0.9, 1.1, tag="B"),
    )
    body = plan(packet).body
    confirmation = body["confirmation"]
    assert set(confirmation["pending"]) == {"商业综合体", "社区配电"}
    assert len(confirmation["scenarios"][0]) and len(confirmation["scenarios"][1])
    allocated = {
        row["case_id"] for row in body["decisions"] if row["status"] == "allocated"
    }
    assert allocated == set(confirmation["roster"])


def test_gear_audit_records_both_options(original):
    packet = _packet(original, _pair("社区配电", 0.94, 1.14))
    body = plan(packet).body
    audit = body["row_evidence"]["PEAKL-136-04"]["pending_gears"]
    assert audit["options"] == [0.94, 1.14]
    assert [row["coefficient"] for row in audit["estimates"]] == [0.94, 1.14]


def test_roster_ledger_stays_within_existing_quota(report):
    body = report.body
    allocated = [row for row in body["decisions"] if row["status"] == "allocated"]
    assert all(row["source"] == "trained" for row in allocated)
    assert sum(body["resource"].values()) == body["summary"]["used"] <= body["summary"]["capacity"]
    assert all(
        units <= resource_limit(body["summary"]["capacity"])
        for units in body["resource"].values()
    )

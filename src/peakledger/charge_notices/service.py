from collections import Counter, defaultdict
from pathlib import Path

from .book import (
    MAX_RECORDS,
    arrival_reason,
    coefficient,
    observation,
    outcome,
    read_stream,
)
from .contracts import Coefficient, Intake, Observation, Outcome, Rejection


def sample(root: Path) -> dict:
    return {
        "observations": read_stream(
            root / "sample_data" / "charge_notices_archive.jsonl"
        ),
        "outcomes": read_stream(
            root / "sample_data" / "billing_holdout_outcomes.jsonl"
        ),
    }


def stage(packet: dict, as_of: int) -> Intake:
    allowed = {"observations", "outcomes", "coefficients"}
    if (
        not isinstance(packet, dict)
        or not {"observations", "outcomes"} <= set(packet)
        or set(packet) - allowed
    ):
        raise ValueError("批次应包含 observations 和 outcomes 两份记录")
    if type(as_of) is not int or not 2 <= as_of <= 36_500:
        raise ValueError("批次日超出接受范围")
    for stream in packet.values():
        if not isinstance(stream, list) or len(stream) > MAX_RECORDS:
            raise ValueError(f"每份记录须为列表，最多 {MAX_RECORDS} 条")
    rejection_counts = Counter()

    def reject(code, stream, case_id, detail, count=1):
        rejection_counts[code, stream, case_id, detail] += count

    revisions: dict[str, list[Observation]] = defaultdict(list)
    for row in packet["observations"]:
        try:
            entry = observation(row)
        except ValueError as exc:
            label = row.get("case_id", "—") if isinstance(row, dict) else "—"
            reject("INVALID", "observation", str(label)[:44], str(exc))
            continue
        reason = arrival_reason(entry, as_of)
        if reason:
            reject(reason, "observation", entry.case_id, "这笔记录在本次裁决时不可见")
        else:
            revisions[entry.case_id].append(entry)

    accepted = {}
    for case_id, entries in sorted(revisions.items()):
        latest = max(item.revision for item in entries)
        top = [item for item in entries if item.revision == latest]
        older = len(entries) - len(top)
        if older:
            reject("SUPERSEDED", "observation", case_id, "已有较新修订", older)
        if any(item != top[0] for item in top[1:]):
            reject(
                "REVISION_CONFLICT",
                "observation",
                case_id,
                "同一修订写入不同测量值",
                len(top),
            )
            continue
        accepted[case_id] = top[0]
        if len(top) > 1:
            reject("EXACT_REPLAY", "observation", case_id, "相同单据重送", len(top) - 1)

    history: dict[str, list[Outcome]] = defaultdict(list)
    for row in packet["outcomes"]:
        try:
            result = outcome(row)
        except ValueError as exc:
            label = row.get("case_id", "—") if isinstance(row, dict) else "—"
            reject("INVALID", "outcome", str(label)[:44], str(exc))
            continue
        obs = accepted.get(result.case_id)
        if result.available > as_of:
            reject("LABEL_NOT_VISIBLE", "outcome", result.case_id, "结案在快照日之后")
        elif obs is None or result.available <= obs.day:
            reject(
                "LABEL_NOT_LINKED",
                "outcome",
                result.case_id,
                "对应单据不可用或结案早于/等于发生日",
            )
        else:
            history[result.case_id].append(result)
    # 保存历次已知结果供每个回放折独立回读，纠正结果不会回填旧训练集。
    outcomes = []
    for case_id, entries in sorted(history.items()):
        by_day = defaultdict(list)
        for result in entries:
            by_day[result.available].append(result)
        for available, same_day in sorted(by_day.items()):
            if any(other != same_day[0] for other in same_day[1:]):
                reject(
                    "LABEL_CONFLICT",
                    "outcome",
                    case_id,
                    f"确认日 {available} 收到相互矛盾的结果",
                    len(same_day),
                )
                # invalidation prevents a previously corrected label from resurrecting.
                outcomes.append(Outcome(case_id, available, -1.0, False))
            else:
                outcomes.append(same_day[0])
                if len(same_day) > 1:
                    reject(
                        "EXACT_REPLAY",
                        "outcome",
                        case_id,
                        "重复结案回执",
                        len(same_day) - 1,
                    )
    entries = tuple(
        sorted(accepted.values(), key=lambda item: (item.day, item.case_id))
    )
    coefficients = _pending_gears(packet.get("coefficients", []), as_of, reject)
    rejections = tuple(
        Rejection(*key, occurrences=count)
        for key, count in sorted(rejection_counts.items())
    )
    return Intake(
        entries,
        tuple(outcomes),
        rejections,
        {k: len(v) for k, v in packet.items()},
        coefficients,
    )


def _pending_gears(rows, as_of, reject):
    """归一化可见的待确认档位：同一组最多保留两个互不相同的系数。

    档位以 ``case_id`` 标识，较新修订覆盖较旧修订；同一修订写入不同系数
    视为冲突并整条隔离。快照日之后才入账的档位对当班不可见，重算也不会
    改变名单。超过两档时保留最近入账的两档并留痕。
    """
    revisions: dict[str, list[Coefficient]] = defaultdict(list)
    for row in rows:
        try:
            entry = coefficient(row)
        except ValueError as exc:
            label = row.get("case_id", "—") if isinstance(row, dict) else "—"
            reject("INVALID", "coefficient", str(label)[:44], str(exc))
            continue
        if entry.arrived > as_of:
            reject(
                "GEAR_LATE",
                "coefficient",
                entry.case_id,
                "档位记录在快照日之后才入账",
            )
            continue
        revisions[entry.case_id].append(entry)

    resolved = []
    for case_id, entries in sorted(revisions.items()):
        latest = max(item.revision for item in entries)
        top = [item for item in entries if item.revision == latest]
        older = len(entries) - len(top)
        if older:
            reject("GEAR_SUPERSEDED", "coefficient", case_id, "已有较新修订", older)
        if any(item.coefficient != top[0].coefficient for item in top[1:]):
            reject(
                "GEAR_CONFLICT",
                "coefficient",
                case_id,
                "同一修订写入不同待确认系数",
                len(top),
            )
            continue
        if len(top) > 1:
            reject(
                "GEAR_REPLAY",
                "coefficient",
                case_id,
                "相同档位重送",
                len(top) - 1,
            )
        resolved.append(top[0])

    by_group: dict[str, list[Coefficient]] = defaultdict(list)
    for item in resolved:
        by_group[item.group].append(item)
    chosen = []
    for group, entries in sorted(by_group.items()):
        distinct: dict[float, Coefficient] = {}
        for item in entries:
            current = distinct.get(item.coefficient)
            if current is None or (item.revision, item.arrived) < (
                current.revision,
                current.arrived,
            ):
                distinct[item.coefficient] = item
        values = sorted(
            distinct.values(),
            key=lambda item: (-item.revision, -item.arrived, item.coefficient),
        )
        if len(values) > 2:
            reject(
                "GEAR_EXCESS",
                "coefficient",
                group,
                "待确认系数超过两档，保留最近两档",
                len(values) - 2,
            )
            values = values[:2]
        chosen.extend(values)
    return tuple(sorted(chosen, key=lambda item: (item.group, item.coefficient)))


def known_labels(intake: Intake, day: int) -> dict[str, Outcome]:
    visible = {item.case_id: item for item in intake.outcomes if item.available <= day}
    return {case_id: label for case_id, label in visible.items() if label.value >= 0}

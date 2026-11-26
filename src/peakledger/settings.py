PROJECT_NAME = "需量罚费账单复核"
ROLE = "园区能源对账员"
MODEL_LABEL = "正则化逻辑回归"
TARGET = "binary"
UNIT = "概率"
ACTION_LABEL = "移交需量罚费复核"
RESERVE_LABEL = "按计量组复核席位"
DEFAULT_DAY = 144
DEFAULT_BUDGET = 16
REPORT_LAG = 1
GROUPS = ("冷冻加工", "轻型机加", "商业综合体", "社区配电")
SIGNAL_NAMES = ("over_limit", "gap_fraction", "meter_delta", "fee_exposure")
WATCH_FEATURE = "over_limit"
METRIC_LABEL = "Brier 分数"
FIELD_LABELS = {
    "observed_kw": "账期最大需量 kW",
    "subscribed_kw": "签约需量 kW",
    "gap_min": "采集间隙 min",
    "multiplicity": "互感器校验系数",
    "fee": "需量罚费 元",
    "amendment": "费率已生效",
    "locked": "账单冻结",
}
FIELD_BOUNDS = {
    "observed_kw": (75, 680),
    "subscribed_kw": (100, 580),
    "gap_min": (0, 29),
    "multiplicity": (0.7, 1.32),
    "fee": (30, 3400),
    "amendment": (0, 1),
    "locked": (0, 1),
}
CRITICAL_FIELDS = frozenset(("amendment", "locked", "observed_kw"))

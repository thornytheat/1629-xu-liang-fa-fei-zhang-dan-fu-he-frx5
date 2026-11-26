from dataclasses import dataclass, field


@dataclass(frozen=True)
class Observation:
    case_id: str
    group: str
    day: int
    arrived: int
    revision: int
    clock: int
    reported: dict[str, float | None]


@dataclass(frozen=True)
class Outcome:
    case_id: str
    available: int
    value: float
    occurred: bool


@dataclass(frozen=True)
class Coefficient:
    """换档后某计量组待确认的互感器校验系数。

    同一组最多保留两个可见值；整组最终只会采用其中一档。
    """

    case_id: str
    group: str
    coefficient: float
    day: int
    revision: int
    arrived: int


@dataclass(frozen=True)
class Rejection:
    code: str
    stream: str
    case_id: str
    detail: str
    occurrences: int = 1


@dataclass(frozen=True)
class Intake:
    observations: tuple[Observation, ...]
    outcomes: tuple[Outcome, ...]
    rejections: tuple[Rejection, ...]
    source_counts: dict[str, int]
    coefficients: tuple[Coefficient, ...] = field(default_factory=tuple)

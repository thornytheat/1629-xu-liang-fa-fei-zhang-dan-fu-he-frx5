from dataclasses import dataclass

from ..charge_notices.contracts import Outcome
from ..tariff_signature.contracts import Signal


@dataclass(frozen=True)
class LearningRow:
    signal: Signal
    outcome: Outcome

    @property
    def y(self) -> float:
        return self.outcome.value

    @property
    def x(self) -> tuple[float, ...]:
        return self.signal.normalized

    @property
    def raw(self) -> tuple[float, ...]:
        return self.signal.vector


@dataclass(frozen=True)
class Fit:
    state: dict | None
    support: int
    incumbent: float
    by_group: dict[str, float]
    training_cases: tuple[str, ...]
    warnings: tuple[str, ...]

from __future__ import annotations

import math
from bisect import bisect_right
from dataclasses import dataclass
from statistics import median


@dataclass(frozen=True)
class BeatGrid:
    """Instantes (em segundos, no tempo da música) de cada batida.

    Batidas fracionárias são interpoladas (2.5 = meio caminho entre a batida 2 e a 3)
    e valores fora da grade são extrapolados pelo período mediano.
    """

    times: tuple[float, ...]

    def __post_init__(self) -> None:
        if len(self.times) < 2:
            raise ValueError("a grade precisa de pelo menos 2 batidas")
        if any(b <= a for a, b in zip(self.times, self.times[1:])):
            raise ValueError("as batidas precisam estar em ordem crescente")

    @classmethod
    def regular(cls, bpm: float, count: int, offset: float = 0.0) -> BeatGrid:
        step = 60.0 / bpm
        return cls(tuple(offset + i * step for i in range(count)))

    @property
    def period(self) -> float:
        return median(b - a for a, b in zip(self.times, self.times[1:]))

    @property
    def bpm(self) -> float:
        return 60.0 / self.period

    def __len__(self) -> int:
        return len(self.times)

    def time(self, beat: float) -> float:
        """Segundo em que a batida `beat` acontece."""
        last = len(self.times) - 1
        if beat < 0:
            return self.times[0] + beat * self.period
        if beat >= last:
            return self.times[-1] + (beat - last) * self.period
        i = int(math.floor(beat))
        frac = beat - i
        return self.times[i] + frac * (self.times[i + 1] - self.times[i])

    def beat(self, t: float) -> float:
        """Inverso de `time`: batida (fracionária) no segundo `t`."""
        if t < self.times[0]:
            return (t - self.times[0]) / self.period
        if t >= self.times[-1]:
            return len(self.times) - 1 + (t - self.times[-1]) / self.period
        i = bisect_right(self.times, t) - 1
        return i + (t - self.times[i]) / (self.times[i + 1] - self.times[i])

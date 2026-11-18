from __future__ import annotations

from dataclasses import dataclass, field

from .beatgrid import BeatGrid


@dataclass(frozen=True)
class TrackAnalysis:
    """O que o reelbeat sabe da música, tudo em índices de batida.

    - hits: impactos (a energia sobe de repente)
    - risers: subidas (start, hit): batidas que crescem até desaguar num impacto
    - drop: primeiro grande aumento de energia (onde o vídeo "explode")
    - sections: batidas onde a textura da música muda
    """

    grid: BeatGrid
    duration: float
    hits: tuple[int, ...] = ()
    risers: tuple[tuple[int, int], ...] = ()
    drop: int | None = None
    sections: tuple[int, ...] = field(default_factory=tuple)

    @property
    def major_hits(self) -> tuple[int, ...]:
        """Impactos que vêm depois de uma subida: os melhores pontos de virada."""
        return tuple(sorted({h for _, h in self.risers}))

    def riser_into(self, hit: int) -> tuple[int, int] | None:
        return next((r for r in self.risers if r[1] == hit), None)

    def to_dict(self) -> dict:
        return {
            "tempo": round(self.grid.bpm, 3),
            "duration": round(self.duration, 3),
            "drop": self.drop,
            "hits": list(self.hits),
            "risers": [list(r) for r in self.risers],
            "sections": list(self.sections),
            "beats": [round(t, 4) for t in self.grid.times],
        }

    @classmethod
    def from_dict(cls, data: dict) -> TrackAnalysis:
        return cls(
            grid=BeatGrid(tuple(float(t) for t in data["beats"])),
            duration=float(data["duration"]),
            hits=tuple(int(h) for h in data.get("hits", ())),
            risers=tuple((int(a), int(b)) for a, b in data.get("risers", ())),
            drop=data.get("drop"),
            sections=tuple(int(s) for s in data.get("sections", ())),
        )

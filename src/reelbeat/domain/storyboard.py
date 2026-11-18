from __future__ import annotations

import math
from dataclasses import dataclass, field

from .beatgrid import BeatGrid
from .layout import Layout

COLORS = ("black", "white", "red", "green", "blue")
MOTIONS = ("in", "out", "punch", "still")


def _check_color(name: str) -> str:
    if name not in COLORS:
        raise ValueError(f"cor desconhecida: {name!r} (use {', '.join(COLORS)})")
    return name


@dataclass(frozen=True)
class Card:
    """Tela de texto sobre cor sólida. `push` aplica um zoom lento (para títulos)."""

    layout: Layout
    bg: str = "black"
    fg: str | None = None
    push: bool = False

    def __post_init__(self) -> None:
        _check_color(self.bg)
        if self.fg is not None:
            _check_color(self.fg)


@dataclass(frozen=True)
class Photo:
    """Foto em tela cheia. motion: in (aproxima), out (afasta), punch (soco no corte), still (parada)."""

    file: str
    motion: str = "punch"

    def __post_init__(self) -> None:
        if self.motion not in MOTIONS:
            raise ValueError(f"movimento desconhecido: {self.motion!r} (use {', '.join(MOTIONS)})")


@dataclass(frozen=True)
class Ramp:
    """Aceleração de um vídeo: a partir da batida `at`, acelera até chegar ao segundo `to` do arquivo."""

    at: float
    to: float


@dataclass(frozen=True)
class Clip:
    """Trecho de vídeo. `start` é o segundo do arquivo onde começa; `speed` é a velocidade (2 = 2x)."""

    file: str
    start: float = 0.0
    speed: float = 1.0
    ramp: Ramp | None = None

    def __post_init__(self) -> None:
        if self.speed <= 0:
            raise ValueError("a velocidade do vídeo precisa ser maior que zero")


@dataclass(frozen=True)
class Knock:
    """Vídeo aparecendo só por dentro das letras de um texto, sobre preto."""

    clip: Clip
    layout: Layout


@dataclass(frozen=True)
class Burst:
    """Rajada de fotos trocando a cada `step` batidas (0.25 = quatro por batida)."""

    files: tuple[str, ...]
    step: float = 0.25

    def __post_init__(self) -> None:
        if not self.files:
            raise ValueError("a rajada precisa de pelo menos uma foto")
        if self.step <= 0:
            raise ValueError("o passo da rajada precisa ser maior que zero")


@dataclass(frozen=True)
class Strobe:
    """Estrobo RGB: a cor troca 8 vezes por batida; o layout troca a cada `step` batidas."""

    layouts: tuple[Layout, ...]
    step: float = 1.0

    def __post_init__(self) -> None:
        if not self.layouts:
            raise ValueError("o estrobo precisa de pelo menos um layout")


@dataclass(frozen=True)
class ColorCards:
    """O mesmo texto em cores diferentes, uma a cada `step` batidas (cartela de capítulo)."""

    layout: Layout
    colors: tuple[str, ...] = ("red", "green", "blue")
    step: float = 1.0

    def __post_init__(self) -> None:
        for c in self.colors:
            _check_color(c)


@dataclass(frozen=True)
class StrobeBeat:
    """Um passo do estrobo (gerado por `expand`)."""

    layout: Layout


Item = Card | Photo | Clip | Knock | Burst | Strobe | ColorCards
Atomic = Card | Photo | Clip | Knock | StrobeBeat


@dataclass(frozen=True)
class Entry:
    """Um item do roteiro que começa na batida `at` (None = início do vídeo) e vai até o próximo."""

    at: float | None
    item: Item


@dataclass
class Storyboard:
    audio: str
    entries: list[Entry]
    end: float
    audio_start: float = 0.0
    width: int = 1080
    height: int = 1920
    fps: int = 30
    fade_out: float = 0.9
    analysis: str | None = None
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Segment:
    """Trecho atômico já em segundos do vídeo (0 = primeiro frame)."""

    t0: float
    t1: float
    item: Atomic


def _beat_span(at: float | None, grid: BeatGrid, offset: float) -> float:
    return grid.beat(offset) if at is None else at


def expand(sb: Storyboard, grid: BeatGrid) -> list[Segment]:
    """Transforma o roteiro (em batidas) numa lista contínua de trechos (em segundos)."""
    entries = sorted(sb.entries, key=lambda e: -math.inf if e.at is None else e.at)
    starts = [e.at for e in entries if e.at is not None]
    if len(starts) != len(set(starts)):
        raise ValueError("dois itens do roteiro começam na mesma batida")
    if sum(1 for e in entries if e.at is None) > 1:
        raise ValueError("só um item pode começar em 'start'")
    if not entries:
        raise ValueError("o roteiro está vazio")
    if entries[-1].at is not None and entries[-1].at >= sb.end:
        raise ValueError("o último item começa depois do fim do vídeo (end)")

    off = sb.audio_start
    to_t = lambda beat: grid.time(beat) - off  # noqa: E731
    segments: list[Segment] = []
    for i, entry in enumerate(entries):
        b0 = _beat_span(entry.at, grid, off)
        b1 = entries[i + 1].at if i + 1 < len(entries) else sb.end
        t0 = 0.0 if entry.at is None else to_t(b0)
        t1 = to_t(b1)
        if t1 <= t0:
            raise ValueError(f"item na batida {entry.at} não tem duração")
        item = entry.item
        if isinstance(item, (Burst, Strobe, ColorCards)):
            seq = (
                item.files if isinstance(item, Burst)
                else item.layouts if isinstance(item, Strobe)
                else item.colors
            )
            k = 0
            while True:
                s0 = b0 + k * item.step
                if s0 >= b1 - 1e-9:
                    break
                s1 = min(b1, s0 + item.step)
                el = seq[k % len(seq)]
                if isinstance(item, Burst):
                    atom: Atomic = Photo(el, "still")
                elif isinstance(item, Strobe):
                    atom = StrobeBeat(el)
                else:
                    atom = Card(item.layout, bg=el)
                segments.append(Segment(t0 if k == 0 else to_t(s0), to_t(s1), atom))
                k += 1
        else:
            segments.append(Segment(t0, t1, item))
    return segments

"""Calcula cada quadro do vídeo a partir do roteiro."""

from __future__ import annotations

import random
from pathlib import Path

import cv2
import numpy as np

from ..domain import BeatGrid, Card, Clip, Knock, Photo, Segment, Storyboard, StrobeBeat, expand
from ..media import ClipFrames, ClipStore, PhotoStore
from .typeset import Typesetter

RGB = {
    "black": (0, 0, 0),
    "white": (255, 255, 255),
    "red": (255, 0, 0),
    "green": (0, 255, 0),
    "blue": (0, 0, 255),
}
# cor do texto sobre cada fundo (o "quebra" das cartelas RGB)
PAIR = {"red": "blue", "green": "red", "blue": "green", "black": "white", "white": "black"}
STROBE_COLORS = ("red", "green", "blue")


def strobe_sequence(n: int = 4096, seed: int = 7) -> list[str]:
    rng, prev, seq = random.Random(seed), None, []
    for _ in range(n):
        prev = rng.choice([c for c in STROBE_COLORS if c != prev])
        seq.append(prev)
    return seq


class Compositor:
    def __init__(self, storyboard: Storyboard, grid: BeatGrid, base: Path, cache_dir: Path):
        self.sb, self.grid = storyboard, grid
        self.W, self.H = storyboard.width, storyboard.height
        self.text = Typesetter(self.W, self.H)
        self.photos = PhotoStore(base, self.W, self.H)
        self.clips = ClipStore(base, cache_dir, self.W, self.H)
        self.segments: list[Segment] = expand(storyboard, grid)
        self.duration = grid.time(storyboard.end) - storyboard.audio_start
        self._strobe = strobe_sequence()
        self._solid: dict[str, np.ndarray] = {}
        self._clip_frames: dict[int, ClipFrames] = {}
        self._cursor = 0

    # ----------------------------------------------------------- preparação
    def source_time(self, clip: Clip, seg: Segment, t: float) -> float:
        """Segundo do arquivo de vídeo mostrado no instante t do vídeo final."""
        if clip.ramp is None:
            return clip.start + clip.speed * (t - seg.t0)
        tr = min(max(self.grid.time(clip.ramp.at) - self.sb.audio_start, seg.t0), seg.t1)
        v = clip.speed
        if t < tr:
            return clip.start + v * (t - seg.t0)
        s_r = clip.start + v * (tr - seg.t0)
        d = max(seg.t1 - tr, 1e-6)
        a = 2 * (clip.ramp.to - s_r - v * d) / (d * d)
        u = t - tr
        return s_r + v * u + 0.5 * a * u * u

    def prepare(self, progress=None) -> None:
        """Extrai (uma vez, com cache) os quadros dos vídeos usados."""
        todo = [(i, s) for i, s in enumerate(self.segments) if isinstance(s.item, (Clip, Knock))]
        for n, (i, seg) in enumerate(todo, 1):
            clip = seg.item.clip if isinstance(seg.item, Knock) else seg.item
            s0 = self.source_time(clip, seg, seg.t0)
            s1 = self.source_time(clip, seg, seg.t1)
            ts = np.linspace(seg.t0, seg.t1, 16)
            speeds = np.abs(np.diff([self.source_time(clip, seg, x) for x in ts])) / np.diff(ts)
            min_speed = max(0.05, float(speeds.min()))
            sample_fps = self.sb.fps / min_speed
            self._clip_frames[i] = self.clips.frames(clip.file, min(s0, s1), max(s0, s1) + 0.1, sample_fps)
            if progress:
                progress(n, len(todo), clip.file)

    # -------------------------------------------------------------- quadros
    def _solid_rgb(self, name: str) -> np.ndarray:
        if name not in self._solid:
            self._solid[name] = np.full((self.H, self.W, 3), RGB[name], np.uint8)
        return self._solid[name]

    def _comp(self, bg: str, mask: np.ndarray, fg: str | None = None) -> np.ndarray:
        b = np.array(RGB[bg], np.float32)
        f = np.array(RGB[fg or PAIR[bg]], np.float32)
        out = b + (f - b) * mask[..., None]
        return out.astype(np.uint8)

    def _segment_at(self, t: float) -> tuple[int, Segment]:
        segs = self.segments
        i = self._cursor if self._cursor < len(segs) and segs[self._cursor].t0 <= t else 0
        while i + 1 < len(segs) and segs[i].t1 <= t:
            i += 1
        self._cursor = i
        return i, segs[i]

    def frame(self, t: float) -> np.ndarray:
        i, seg = self._segment_at(t)
        it = seg.item
        p = (t - seg.t0) / max(seg.t1 - seg.t0, 1e-6)
        if isinstance(it, Card):
            mask = self.text.mask(it.layout)
            if it.push:
                A = cv2.getRotationMatrix2D((self.W / 2, self.H / 2), 0, 1.0 + 0.05 * p)
                mask = cv2.warpAffine(mask, A, (self.W, self.H), flags=cv2.INTER_LINEAR)
            return self._comp(it.bg, mask, it.fg)
        if isinstance(it, Photo):
            if it.motion == "in":
                z = 1.0 + 0.06 * p
            elif it.motion == "out":
                z = 1.06 - 0.06 * p
            elif it.motion == "punch":
                z = 1.0 + 0.02 * p + 0.06 * float(np.exp(-(t - seg.t0) / 0.09))
            else:
                z = 1.04
            return self.photos.frame(it.file, z)
        if isinstance(it, Clip):
            return self._clip_frames[i].at(self.source_time(it, seg, t))
        if isinstance(it, Knock):
            A = cv2.getRotationMatrix2D((self.W / 2, self.H / 2), 0, 1.0 + 0.04 * p)
            mask = cv2.warpAffine(self.text.mask(it.layout), A, (self.W, self.H), flags=cv2.INTER_LINEAR)
            img = self._clip_frames[i].at(self.source_time(it.clip, seg, t)).astype(np.float32)
            return (img * mask[..., None]).astype(np.uint8)
        if isinstance(it, StrobeBeat):
            beat0 = self.grid.time(0) - self.sb.audio_start
            slot = int((t - beat0) / (self.grid.period / 8))
            color = self._strobe[slot % len(self._strobe)]
            sub = int((t - seg.t0) / (self.grid.period / 8))
            if it.layout.type == "blank" or sub % 4 == 3:  # o texto pisca a cada 4 trocas de cor
                return self._solid_rgb(color)
            return self._comp(color, self.text.mask(it.layout))
        raise TypeError(f"item desconhecido: {it!r}")

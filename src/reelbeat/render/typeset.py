"""Desenha os layouts de texto como máscaras (0..1) do tamanho do vídeo."""

from __future__ import annotations

from importlib import resources

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from ..domain import Layout

ANTON = "Anton-Regular.ttf"
ARCHIVO = "ArchivoBlack-Regular.ttf"
MONO = "SpaceMono-Bold.ttf"


def font_path(name: str) -> str:
    return str(resources.files("reelbeat") / "assets" / "fonts" / name)


class Typesetter:
    def __init__(self, width: int, height: int):
        self.W, self.H = width, height
        self.s = width / 1080.0
        self._words: dict[tuple, np.ndarray] = {}
        self._masks: dict[str, np.ndarray] = {}
        self._fonts: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}
        ref = self.word("SEGURO", ANTON, 260)
        self._big_k = (780 * self.s) / ref.shape[1]  # todos os títulos "big" com a mesma altura de letra

    # ----------------------------------------------------------------- base
    def _font(self, name: str, size: int) -> ImageFont.FreeTypeFont:
        key = (name, max(1, int(size)))
        if key not in self._fonts:
            self._fonts[key] = ImageFont.truetype(font_path(name), key[1])
        return self._fonts[key]

    def word(self, text: str, font: str, size: float, spacing: float = 0) -> np.ndarray:
        """Máscara justa do texto (pode ter várias linhas separadas por \\n)."""
        key = (text, font, int(size), int(spacing))
        if key not in self._words:
            f = self._font(font, int(size))
            probe = ImageDraw.Draw(Image.new("L", (8, 8)))
            bb = [int(round(v)) for v in probe.multiline_textbbox((0, 0), text, font=f, align="center",
                                                                  spacing=int(spacing))]
            im = Image.new("L", (bb[2] - bb[0] + 4, bb[3] - bb[1] + 4), 0)
            ImageDraw.Draw(im).multiline_text((2 - bb[0], 2 - bb[1]), text, font=f, fill=255, align="center",
                                              spacing=int(spacing))
            self._words[key] = np.asarray(im, dtype=np.float32) / 255.0
        return self._words[key]

    @staticmethod
    def _resize(m: np.ndarray, w: float, h: float) -> np.ndarray:
        w, h = max(1, int(w)), max(1, int(h))
        interp = cv2.INTER_AREA if w < m.shape[1] else cv2.INTER_LINEAR
        return cv2.resize(m, (w, h), interpolation=interp)

    def _fit_w(self, m: np.ndarray, w: float) -> np.ndarray:
        return self._resize(m, w, m.shape[0] * w / m.shape[1])

    def _place(self, canvas: np.ndarray, m: np.ndarray, cx: float, cy: float) -> None:
        h, w = m.shape
        x0, y0 = int(cx - w / 2), int(cy - h / 2)
        xs, ys, xe, ye = max(0, x0), max(0, y0), min(self.W, x0 + w), min(self.H, y0 + h)
        if xe > xs and ye > ys:
            region = canvas[ys:ye, xs:xe]
            np.maximum(region, m[ys - y0:ye - y0, xs - x0:xe - x0], out=region)

    # -------------------------------------------------------------- layouts
    def mask(self, layout: Layout | str) -> np.ndarray:
        layout = Layout.parse(layout)
        key = str(layout)
        if key in self._masks:
            return self._masks[key]
        W, H, s = self.W, self.H, self.s
        c = np.zeros((H, W), np.float32)
        lines = layout.lines
        t = layout.type
        if t == "small":
            self._place(c, self.word("\n".join(lines), MONO, 46 * s, spacing=14 * s), W / 2, H / 2)
        elif t == "big":
            m = self.word("\n".join(lines), ANTON, 260, spacing=-30)
            k = min(self._big_k, (940 * s) / m.shape[1])
            self._place(c, self._resize(m, m.shape[1] * k, m.shape[0] * k), W / 2, H / 2)
        elif t == "tall":
            hh = H * 0.86 / len(lines)
            for i, line in enumerate(lines):
                m = self._resize(self.word(line, ANTON, 300), W * 0.9, hh * 0.94)
                self._place(c, m, W / 2, H * 0.07 + hh * (i + 0.5))
        elif t == "stack":
            m = self._fit_w(self.word(" ".join(lines), ARCHIVO, 200), 820 * s)
            gap = m.shape[0] * 1.05
            for i in range(layout.n):
                self._place(c, m, W / 2, H / 2 + (i - (layout.n - 1) / 2) * gap)
        elif t == "split":
            if len(lines) == 1:
                w = lines[0]
                lines = [w[: len(w) // 2], w[len(w) // 2:]]
            top = self._fit_w(self.word(lines[0], ARCHIVO, 200), 760 * s)
            bottom = self._fit_w(self.word(" ".join(lines[1:]), ARCHIVO, 200), 760 * s)
            self._place(c, top, W / 2, H * 0.16)
            self._place(c, bottom, W / 2, H * 0.84)
        elif t == "grid":
            m = self._fit_w(self.word(" ".join(lines), ARCHIVO, 120), W / layout.cols * 0.8)
            for r in range(layout.rows):
                for k in range(layout.cols):
                    self._place(c, m, (k + 0.5) * W / layout.cols, (r + 0.5) * H / layout.rows)
        elif t == "rows":
            text = " ".join(lines)
            m = self.word(f"{text}   {text}", ANTON, 330 * s)
            for r in range(layout.n):
                cx = W / 2 + (r % 2) * 0.33 * m.shape[1] - 0.15 * m.shape[1]
                self._place(c, m, cx, (r + 0.5) * H / layout.n)
        # "blank": máscara vazia
        self._masks[key] = c
        return c

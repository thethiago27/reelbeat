"""Cartelas estáticas (PNG) com um texto em fundos RGB e preto/branco, para usar em qualquer editor."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from ..domain import Layout
from .compositor import PAIR, RGB
from .typeset import Typesetter

SCHEMES = ("red", "green", "blue", "black", "white")
NAMES_PT = {"red": "vermelho", "green": "verde", "blue": "azul", "black": "preto", "white": "branco"}


def export_cards(text: str, out_dir: Path, layout: str = "big", width: int = 1080, height: int = 1920) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = Typesetter(width, height)
    mask = ts.mask(Layout.parse(f"{layout}: {text}"))
    files = []
    slug = "".join(ch if ch.isalnum() else "_" for ch in text).strip("_") or "card"
    for bg in SCHEMES:
        b, f = RGB[bg], RGB[PAIR[bg]]
        img = Image.new("RGB", (width, height), b)
        fg = Image.new("RGB", (width, height), f)
        img.paste(fg, mask=Image.fromarray((mask * 255).astype("uint8")))
        path = out_dir / f"{slug}_{NAMES_PT[bg]}.png"
        img.save(path)
        files.append(path)
    return files

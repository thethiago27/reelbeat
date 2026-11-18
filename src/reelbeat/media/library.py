"""Varre a pasta de mídia. Cada subpasta vira um capítulo, na ordem do nome.

    midia/
      01-porto-seguro/   -> capítulo "PORTO SEGURO"
      02-arraial/        -> capítulo "ARRAIAL"
      03-trancoso/       -> capítulo "TRANCOSO"

Sem subpastas, a pasta inteira vira um capítulo só.
Dentro de cada capítulo, os arquivos seguem a ordem em que foram feitos (EXIF / metadados),
ou a ordem do nome quando a data não existe.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from PIL import Image

from .probe import probe_video

PHOTO_EXT = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp"}
VIDEO_EXT = {".mov", ".mp4", ".m4v"}

try:  # HEIC do iPhone
    import pillow_heif

    pillow_heif.register_heif_opener()
except ImportError:  # pragma: no cover
    pass


@dataclass(frozen=True)
class MediaItem:
    path: Path
    kind: str  # "photo" | "video"
    taken_at: datetime | None = None
    duration: float | None = None

    @property
    def is_video(self) -> bool:
        return self.kind == "video"


@dataclass
class Chapter:
    name: str
    items: list[MediaItem] = field(default_factory=list)

    @property
    def photos(self) -> list[MediaItem]:
        return [i for i in self.items if not i.is_video]

    @property
    def videos(self) -> list[MediaItem]:
        return [i for i in self.items if i.is_video]


def chapter_name(folder: str) -> str:
    """'02-arraial_dajuda' -> 'ARRAIAL DAJUDA'."""
    name = re.sub(r"^\d+[\s._-]*", "", folder)
    name = re.sub(r"[_-]+", " ", name).strip()
    return (name or folder).upper()


def _photo_date(path: Path) -> datetime | None:
    try:
        with Image.open(path) as im:
            exif = im.getexif()
            raw = exif.get_ifd(0x8769).get(36867) or exif.get(306)
        return datetime.strptime(str(raw), "%Y:%m:%d %H:%M:%S") if raw else None
    except Exception:
        return None


def _item(path: Path) -> MediaItem | None:
    ext = path.suffix.lower()
    if ext in PHOTO_EXT:
        return MediaItem(path, "photo", _photo_date(path))
    if ext in VIDEO_EXT:
        info = probe_video(str(path))
        return MediaItem(path, "video", info.created, info.duration)
    return None


def _ordered(items: list[MediaItem]) -> list[MediaItem]:
    if items and all(i.taken_at for i in items):
        return sorted(items, key=lambda i: (i.taken_at, i.path.name))
    return sorted(items, key=lambda i: i.path.name.lower())


def _collect(folder: Path) -> list[MediaItem]:
    found = (_item(p) for p in sorted(folder.iterdir()) if p.is_file() and not p.name.startswith("."))
    return _ordered([i for i in found if i is not None])


def scan(root: str | Path, names: list[str] | None = None) -> list[Chapter]:
    root = Path(root)
    if not root.is_dir():
        raise FileNotFoundError(f"pasta de mídia não encontrada: {root}")
    subdirs = [d for d in sorted(root.iterdir()) if d.is_dir() and not d.name.startswith(".")]
    chapters = [Chapter(chapter_name(d.name), _collect(d)) for d in subdirs]
    chapters = [c for c in chapters if c.items]
    if not chapters:
        chapters = [Chapter(chapter_name(root.name), _collect(root))]
    if not chapters[0].items:
        raise ValueError(f"nenhuma foto ou vídeo encontrado em {root}")
    if names:
        if len(names) != len(chapters):
            raise ValueError(f"foram dados {len(names)} nomes para {len(chapters)} capítulos")
        for c, n in zip(chapters, names):
            c.name = n.strip().upper()
    return chapters

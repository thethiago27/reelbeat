from __future__ import annotations

from collections import OrderedDict
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

try:
    import pillow_heif

    pillow_heif.register_heif_opener()
except ImportError:  # pragma: no cover
    pass

MARGIN = 1.12  # sobra em volta do quadro para os zooms


def cover(img: np.ndarray, width: int, height: int) -> np.ndarray:
    """Redimensiona e corta ao centro para preencher width x height (sem barras)."""
    h, w = img.shape[:2]
    s = max(width / w, height / h)
    nw, nh = max(width, round(w * s)), max(height, round(h * s))
    img = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC)
    y0, x0 = (nh - height) // 2, (nw - width) // 2
    return img[y0:y0 + height, x0:x0 + width]


def zoom(buffer: np.ndarray, z: float, width: int, height: int) -> np.ndarray:
    """Recorta o centro do buffer (que tem MARGIN x o quadro) com zoom z (1 = quadro inteiro)."""
    h, w = buffer.shape[:2]
    z = max(z, 1.0 / MARGIN)
    cw, ch = min(w, int(w / (MARGIN * z))), min(h, int(h / (MARGIN * z)))
    x0, y0 = (w - cw) // 2, (h - ch) // 2
    return cv2.resize(buffer[y0:y0 + ch, x0:x0 + cw], (width, height), interpolation=cv2.INTER_LINEAR)


class PhotoStore:
    """Carrega fotos (JPG, PNG, HEIC...) já giradas pelo EXIF e cortadas para o formato do vídeo."""

    def __init__(self, base: Path, width: int, height: int, capacity: int = 48):
        self.base, self.width, self.height = Path(base), width, height
        self._cache: OrderedDict[str, np.ndarray] = OrderedDict()
        self._capacity = capacity

    def resolve(self, file: str) -> Path:
        p = Path(file)
        return p if p.is_absolute() else self.base / p

    def buffer(self, file: str) -> np.ndarray:
        if file in self._cache:
            self._cache.move_to_end(file)
            return self._cache[file]
        path = self.resolve(file)
        if not path.exists():
            raise FileNotFoundError(f"foto não encontrada: {path}")
        with Image.open(path) as im:
            rgb = np.asarray(ImageOps.exif_transpose(im).convert("RGB"))
        buf = cover(rgb, int(self.width * MARGIN), int(self.height * MARGIN))
        self._cache[file] = buf
        if len(self._cache) > self._capacity:
            self._cache.popitem(last=False)
        return buf

    def frame(self, file: str, z: float = 1.0) -> np.ndarray:
        return zoom(self.buffer(file), z, self.width, self.height)

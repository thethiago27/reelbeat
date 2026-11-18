from __future__ import annotations

import cv2
import numpy as np

from .compositor import Compositor


def contact_sheet(comp: Compositor, start: float = 0.0, end: float | None = None, every: float = 0.25,
                  thumb_width: int = 108, cols: int = 16) -> np.ndarray:
    """Folha de contato (RGB) com um quadro a cada `every` segundos, sem precisar renderizar o vídeo."""
    end = comp.duration if end is None else min(end, comp.duration)
    th = int(thumb_width * comp.H / comp.W)
    thumbs = []
    t = start
    while t < end - 1e-6:
        img = cv2.resize(comp.frame(t), (thumb_width, th), interpolation=cv2.INTER_AREA).copy()
        cv2.putText(img, f"{t:.1f}", (3, 13), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 0), 1, cv2.LINE_AA)
        thumbs.append(img)
        t += every
    if not thumbs:
        raise ValueError("intervalo vazio para a prévia")
    while len(thumbs) % cols:
        thumbs.append(np.zeros_like(thumbs[0]))
    rows = [np.hstack(thumbs[i:i + cols]) for i in range(0, len(thumbs), cols)]
    return np.vstack(rows)

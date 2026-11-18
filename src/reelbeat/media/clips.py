from __future__ import annotations

import hashlib
import subprocess
from collections import OrderedDict
from pathlib import Path

import cv2
import numpy as np

from .probe import file_key, probe_video, require_ffmpeg


class ClipFrames:
    """Quadros de um trecho de vídeo, já no tamanho do vídeo final, amostrados a `sample_fps`."""

    def __init__(self, files: list[Path], start: float, sample_fps: float):
        if not files:
            raise ValueError("nenhum quadro extraído do vídeo")
        self.files, self.start, self.sample_fps = files, start, sample_fps
        self._cache: OrderedDict[int, np.ndarray] = OrderedDict()

    def at(self, source_time: float) -> np.ndarray:
        """Quadro no segundo `source_time` do arquivo original (segura o último se passar do fim)."""
        idx = int(round((source_time - self.start) * self.sample_fps))
        idx = min(len(self.files) - 1, max(0, idx))
        if idx not in self._cache:
            img = cv2.imread(str(self.files[idx]))
            self._cache[idx] = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            if len(self._cache) > 90:
                self._cache.popitem(last=False)
        return self._cache[idx]


class ClipStore:
    """Extrai (com ffmpeg) e guarda em cache os quadros dos trechos de vídeo usados no roteiro."""

    def __init__(self, base: Path, cache_dir: Path, width: int, height: int):
        self.base, self.cache_dir, self.width, self.height = Path(base), Path(cache_dir), width, height

    def resolve(self, file: str) -> Path:
        p = Path(file)
        return p if p.is_absolute() else self.base / p

    def frames(self, file: str, start: float, end: float, sample_fps: float) -> ClipFrames:
        require_ffmpeg()
        path = self.resolve(file)
        if not path.exists():
            raise FileNotFoundError(f"vídeo não encontrado: {path}")
        info = probe_video(str(path))
        start = max(0.0, min(start, max(0.0, info.duration - 0.05)))
        end = max(start + 0.05, min(end, info.duration or end))
        sample_fps = max(1.0, min(sample_fps, info.fps or sample_fps))
        key = hashlib.sha1(
            f"{file_key(path)}|{start:.3f}|{end:.3f}|{sample_fps:.3f}|{self.width}x{self.height}".encode()
        ).hexdigest()[:16]
        folder = self.cache_dir / key
        done = folder / ".done"
        if not done.exists():
            folder.mkdir(parents=True, exist_ok=True)
            for old in folder.glob("*.jpg"):
                old.unlink()
            vf = (
                f"fps={sample_fps:.4f},scale={self.width}:{self.height}:force_original_aspect_ratio=increase,"
                f"crop={self.width}:{self.height}"
            )
            subprocess.run(
                [
                    "ffmpeg", "-y", "-loglevel", "error", "-ss", f"{start:.3f}", "-t", f"{end - start:.3f}",
                    "-i", str(path), "-vf", vf, "-q:v", "2", str(folder / "%05d.jpg"),
                ],
                check=True,
            )
            done.touch()
        return ClipFrames(sorted(folder.glob("*.jpg")), start, sample_fps)

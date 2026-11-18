from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from PIL import Image

from reelbeat.domain import BeatGrid, TrackAnalysis

HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


@pytest.fixture
def grid() -> BeatGrid:
    return BeatGrid.regular(bpm=120, count=200, offset=0.5)


@pytest.fixture
def analysis(grid: BeatGrid) -> TrackAnalysis:
    """Música sintética de 120 BPM: drop na 32, subidas desaguando a cada 16 batidas."""
    risers = tuple((h - 4, h) for h in range(60, 190, 16))
    hits = tuple(sorted({32, 44} | {h for _, h in risers}))
    return TrackAnalysis(grid=grid, duration=100.0, hits=hits, risers=risers, drop=32)


def make_photo(path: Path, color=(200, 80, 40), size=(300, 400)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path)
    return path


@pytest.fixture
def media_dir(tmp_path: Path) -> Path:
    root = tmp_path / "midia"
    for ch, n in (("01-porto-seguro", 14), ("02-arraial_dajuda", 10), ("03-trancoso", 8)):
        for i in range(n):
            make_photo(root / ch / f"IMG_{i:04d}.jpg", color=(i * 15 % 255, 90, 160))
    return root

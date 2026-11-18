from __future__ import annotations

import json
from pathlib import Path

from ..domain import TrackAnalysis


def save_analysis(analysis: TrackAnalysis, path: str | Path) -> Path:
    path = Path(path)
    path.write_text(json.dumps(analysis.to_dict(), indent=1), encoding="utf-8")
    return path


def load_analysis(path: str | Path) -> TrackAnalysis:
    return TrackAnalysis.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

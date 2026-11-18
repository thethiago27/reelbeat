from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path


class FFmpegMissing(RuntimeError):
    pass


def require_ffmpeg() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            raise FFmpegMissing(
                f"'{tool}' não foi encontrado. Instale o ffmpeg (ex.: brew install ffmpeg / sudo apt install ffmpeg)."
            )


@dataclass(frozen=True)
class VideoInfo:
    duration: float
    fps: float
    created: datetime | None


def _parse_fps(rate: str) -> float:
    num, _, den = rate.partition("/")
    try:
        return float(num) / float(den or 1)
    except (ValueError, ZeroDivisionError):
        return 30.0


@lru_cache(maxsize=256)
def probe_video(path: str) -> VideoInfo:
    require_ffmpeg()
    out = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=r_frame_rate,duration:format=duration:format_tags=creation_time",
            "-of", "json", path,
        ],
        capture_output=True, text=True, check=True,
    ).stdout
    data = json.loads(out)
    stream = (data.get("streams") or [{}])[0]
    fmt = data.get("format", {})
    duration = float(stream.get("duration") or fmt.get("duration") or 0.0)
    created = None
    stamp = (fmt.get("tags") or {}).get("creation_time")
    if stamp:
        try:
            created = datetime.fromisoformat(stamp.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            created = None
    return VideoInfo(duration=duration, fps=_parse_fps(stream.get("r_frame_rate", "30/1")), created=created)


def file_key(path: Path) -> str:
    st = path.stat()
    return f"{path.resolve()}|{st.st_size}|{int(st.st_mtime)}"

from __future__ import annotations

import math
import subprocess
from pathlib import Path

from ..media.probe import require_ffmpeg
from .compositor import Compositor


def encode_video(comp: Compositor, out: Path, crf: int = 22, progress=None) -> Path:
    """Renderiza o vídeo sem áudio (H.264, yuv420p)."""
    require_ffmpeg()
    sb = comp.sb
    n = int(math.ceil(comp.duration * sb.fps))
    proc = subprocess.Popen(
        [
            "ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
            "-s", f"{sb.width}x{sb.height}", "-r", str(sb.fps), "-i", "-",
            "-c:v", "libx264", "-preset", "medium", "-crf", str(crf), "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", str(out),
        ],
        stdin=subprocess.PIPE,
    )
    assert proc.stdin is not None
    try:
        for i in range(n):
            proc.stdin.write(comp.frame(i / sb.fps).tobytes())
            if progress and (i % sb.fps == 0 or i == n - 1):
                progress(i + 1, n)
    finally:
        proc.stdin.close()
        proc.wait()
    if proc.returncode != 0:
        raise RuntimeError("o ffmpeg falhou ao gerar o vídeo")
    return out


def mux_audio(video: Path, audio: Path, out: Path, audio_start: float, duration: float, fade_out: float) -> Path:
    """Coloca a música no vídeo, a partir de `audio_start`, com fade no final."""
    require_ffmpeg()
    af = []
    if fade_out > 0:
        af = ["-af", f"afade=t=out:st={max(0.0, duration - fade_out):.3f}:d={fade_out:.3f}"]
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error", "-i", str(video), "-ss", f"{audio_start:.3f}", "-i", str(audio),
            "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", *af,
            "-t", f"{duration:.3f}", "-movflags", "+faststart", str(out),
        ],
        check=True,
    )
    return out

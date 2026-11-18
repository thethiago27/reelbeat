import numpy as np
import pytest

from reelbeat.analysis.audio import BeatFeatures, detect_events
from tests.conftest import HAS_FFMPEG


def _features(n=120):
    rms = np.full(n, 0.20)
    peak = np.full(n, 1.0)
    cent = np.full(n, 2600.0)
    rms[32:] = 0.32  # drop na 32
    peak[32] = 1.6
    for h in (64, 96):  # subida de 4 batidas (mais brilho, menos energia) + impacto
        cent[h - 4:h] = 2950
        rms[h - 3:h] = 0.22
        rms[h:h + 2] = 0.36
        peak[h] = 1.5
    return BeatFeatures(rms, peak, cent)


def test_detects_drop_hits_and_risers():
    hits, risers, drop = detect_events(_features())
    assert drop == 32
    assert {64, 96} <= set(hits)
    assert (60, 64) in risers and (92, 96) in risers


def test_flat_track_has_no_events():
    n = 64
    hits, risers, drop = detect_events(BeatFeatures(np.full(n, 0.2), np.full(n, 1.0), np.full(n, 2000.0)))
    assert hits == () and risers == () and drop is None


@pytest.mark.slow
def test_analyze_click_track(tmp_path):
    soundfile = pytest.importorskip("soundfile")
    from reelbeat.analysis import analyze

    sr, bpm, seconds = 22050, 120, 20
    y = np.zeros(sr * seconds, np.float32)
    click = np.sin(2 * np.pi * 1000 * np.arange(int(0.03 * sr)) / sr) * np.hanning(int(0.03 * sr))
    for k in range(int(seconds * bpm / 60)):
        i = int(k * 60 / bpm * sr)
        y[i:i + len(click)] += click.astype(np.float32)
    path = tmp_path / "click.wav"
    soundfile.write(path, y, sr)
    a = analyze(str(path))
    assert a.grid.bpm == pytest.approx(120, rel=0.03)
    assert HAS_FFMPEG or True

"""Análise da música: grade de batidas, impactos, subidas (risers) e drop.

As regras de detecção (`detect_events`) recebem só números por batida, então dá para testar
sem áudio; `analyze` é quem usa o librosa para medir esses números na música.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..domain import BeatGrid, TrackAnalysis

SR = 22050
HOP = 256


@dataclass(frozen=True)
class BeatFeatures:
    rms: np.ndarray  # energia média em cada batida
    peak: np.ndarray  # pico de ataque (onset) em cada batida
    centroid: np.ndarray  # brilho (centroide espectral) em cada batida


def detect_events(f: BeatFeatures, rise: float = 1.10, peak_factor: float = 1.15,
                  riser_brightness: float = 1.05) -> tuple[tuple[int, ...], tuple[tuple[int, int], ...], int | None]:
    """Impactos, subidas e drop a partir das medidas por batida."""
    n = len(f.rms)
    hits = []
    for b in range(3, n - 2):
        after = f.rms[b:b + 2].mean()
        before = f.rms[b - 3:b].mean()
        if before <= 0:
            continue
        # régua local (32 batidas em volta): partes mais fortes da música não apagam as mais calmas
        med_peak = float(np.median(f.peak[max(0, b - 16):b + 16]))
        strong = f.peak[b] >= peak_factor * med_peak
        if (after / before >= rise and strong) or f.peak[b] >= 1.5 * med_peak:
            hits.append(b)
    # tira impactos colados (fica com o mais forte de cada vizinhança de 2 batidas)
    clean: list[int] = []
    for h in hits:
        if clean and h - clean[-1] <= 2:
            if f.peak[h] > f.peak[clean[-1]]:
                clean[-1] = h
        else:
            clean.append(h)

    risers = []
    for h in clean:
        if h < 8:
            continue
        ref = float(np.median(f.centroid[max(0, h - 16):h - 4]))
        window = f.centroid[h - 4:h]
        if ref > 0 and int((window > riser_brightness * ref).sum()) >= 3:
            risers.append((h - 4, h))

    drop = None
    if n >= 24:
        best, limit = 0.0, max(9, min(n - 8, int(n * 0.4)))
        for b in range(8, limit):
            prev = f.rms[b - 8:b].mean()
            ratio = f.rms[b:b + 8].mean() / prev if prev > 0 else 0.0
            if ratio > best:
                best, drop = ratio, b
        if best < 1.15:
            drop = None
    return tuple(clean), tuple(risers), drop


def analyze(path: str, duration: float | None = None) -> TrackAnalysis:
    import librosa  # importado aqui: é pesado e só a análise precisa dele

    y, sr = librosa.load(path, sr=SR, mono=True, duration=duration)
    if len(y) < sr * 4:
        raise ValueError("a música é curta demais para analisar (mínimo 4 s)")
    oenv = librosa.onset.onset_strength(y=y, sr=sr, hop_length=HOP)
    tempo = float(np.atleast_1d(librosa.feature.tempo(onset_envelope=oenv, sr=sr, hop_length=HOP))[0])
    _, frames = librosa.beat.beat_track(onset_envelope=oenv, sr=sr, hop_length=HOP, start_bpm=tempo,
                                        tightness=400)
    times = librosa.frames_to_time(frames, sr=sr, hop_length=HOP)
    times = np.unique(np.round(times, 4))
    if len(times) < 8:
        raise ValueError("não consegui achar as batidas dessa música")
    grid = BeatGrid(tuple(float(t) for t in times))

    rms = librosa.feature.rms(y=y, hop_length=HOP)[0]
    cent = librosa.feature.spectral_centroid(y=y, sr=sr, hop_length=HOP)[0]
    ft = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=HOP)
    m = min(len(oenv), len(rms), len(cent), len(ft))
    rms, cent, ft, oenv = rms[:m], cent[:m], ft[:m], oenv[:m]

    edges = list(times) + [times[-1] + grid.period]
    per = {"rms": [], "peak": [], "cent": []}
    for t0, t1 in zip(edges, edges[1:]):
        sel = (ft >= t0) & (ft < t1)
        if not sel.any():
            sel = np.zeros_like(ft, bool)
            sel[min(m - 1, int(np.searchsorted(ft, t0)))] = True
        per["rms"].append(float(rms[sel].mean()))
        per["peak"].append(float(oenv[sel].max()))
        per["cent"].append(float(cent[sel].mean()))
    feats = BeatFeatures(np.array(per["rms"]), np.array(per["peak"]), np.array(per["cent"]))
    hits, risers, drop = detect_events(feats)

    mfcc = librosa.feature.mfcc(y=y, sr=sr, hop_length=2048)
    k = int(np.clip(len(y) / sr / 15, 3, 16))
    bounds = librosa.frames_to_time(librosa.segment.agglomerative(mfcc, k), sr=sr, hop_length=2048)
    sections = tuple(sorted({int(round(grid.beat(float(t)))) for t in bounds if t > 0.5}))

    return TrackAnalysis(grid=grid, duration=len(y) / sr, hits=hits, risers=risers, drop=drop, sections=sections)

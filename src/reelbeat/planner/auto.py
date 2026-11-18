"""Monta um roteiro automaticamente a partir da análise da música e dos capítulos de mídia.

A gramática de edição (a mesma do vídeo de Porto Seguro):

1. Abertura em preto: textinhos e títulos dos lugares alternando a cada 2 batidas; o subtítulo
   (ex.: o estado) aparece por dentro das letras do primeiro vídeo, que depois abre em tela cheia.
2. Até o drop: fotos calmas (2 batidas, zoom lento) -> rápidas (1 batida) -> rajada (1/4 de batida).
3. Drop: estrobo RGB com os títulos mudando de layout a cada batida.
4. Capítulos: cartela RGB do lugar, fotos de 1 batida com "soco" no corte, 1 batida de estrobo a cada
   3 fotos, vídeos de 2-4 batidas. Em cada subida da música entra uma rajada (ou o vídeo acelera)
   e no impacto entra uma foto "herói" com zoom lento.
5. Final no último grande impacto: título em vermelho, verde, azul, depois branco no preto e crédito.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from ..domain import (
    Burst,
    Card,
    Clip,
    ColorCards,
    Entry,
    Item,
    Knock,
    Layout,
    Photo,
    Ramp,
    Storyboard,
    Strobe,
    TrackAnalysis,
)
from ..domain.layout import two_lines
from ..media import Chapter, MediaItem


@dataclass
class PlanOptions:
    title: str | None = None  # título geral (padrão: nome do 1º capítulo)
    subtitle: str | None = None  # ex.: BAHIA
    tag: str | None = None  # ex.: BA
    tagline: str | None = "UMA VIAGEM POR"
    connectors: list[str] | None = None  # textinhos entre os títulos da abertura
    seconds: float | None = None  # duração alvo; None = decide pela quantidade de mídia
    width: int = 1080
    height: int = 1920
    fps: int = 30


def default_connectors(n: int) -> list[str]:
    if n <= 1:
        return []
    if n == 2:
        return ["E"]
    return ["COM PARADA EM"] + [""] * (n - 3) + ["E"]


def spread(total: int, n: int) -> list[int]:
    """Divide `total` batidas em `n` partes inteiras o mais iguais possível (maiores primeiro)."""
    base, extra = divmod(total, n)
    return [base + (1 if i < extra else 0) for i in range(n)]


@dataclass
class _Unit:
    kind: str  # photo | video | strobe | burst
    beats: int
    media: list[MediaItem] = field(default_factory=list)


class AutoPlanner:
    def __init__(self, analysis: TrackAnalysis, options: PlanOptions | None = None):
        self.a = analysis
        self.g = analysis.grid
        self.opt = options or PlanOptions()
        self.entries: dict[float | None, Item] = {}
        self.notes: list[str] = []
        self._base = Path(".")
        self._toggle = False
        self._all_shown: list[str] = []
        self._durations: dict[str, float] = {}

    # ------------------------------------------------------------ utilidades
    def _rel(self, p: Path | str) -> str:
        return Path(os.path.relpath(os.path.abspath(p), os.path.abspath(self._base))).as_posix()

    def _put(self, at: float | None, item: Item) -> None:
        if at in self.entries:
            raise RuntimeError(f"conflito no roteiro na batida {at}")
        self.entries[at] = item

    def _dt(self, b0: float, b1: float) -> float:
        return self.g.time(b1) - self.g.time(b0)

    def _motion(self, beats: int) -> str:
        if beats < 2:
            return "punch"
        self._toggle = not self._toggle
        return "in" if self._toggle else "out"

    def _clip(self, m: MediaItem, at: float, beats: float, max_speed: float = 4.0) -> Clip:
        dur = m.duration or 0.0
        self._durations[self._rel(m.path)] = dur
        start = round(min(0.5, dur * 0.05), 2)
        span = self._dt(at, at + beats)
        speed = (dur - start - 0.1) / span if span > 0 else 1.0
        return Clip(self._rel(m.path), start, round(min(max_speed, max(0.5, speed)), 2))

    # ------------------------------------------------------------- estrutura
    def _drop(self) -> int:
        d = self.a.drop
        if d is not None and d >= 16:
            return int(d)
        guess = int(round(self.g.beat(14.0) / 4)) * 4
        return max(16, guess)

    def _natural_seconds(self, queues: list[list[MediaItem]], drop_end: int) -> float:
        n_photos = sum(1 for q in queues for m in q if not m.is_video)
        n_videos = sum(1 for q in queues for m in q if m.is_video)
        beats = n_photos * 1.4 + n_videos * 3 + 3 * (len(queues) - 1) + 12
        return self.g.time(drop_end + beats) - self.g.time(0)

    def _final_hit(self, start: int, target: float) -> int:
        last_ok = len(self.g) - 9
        end_t = lambda h: self.g.time(h + 8)  # noqa: E731
        cands = [h for h in self.a.major_hits if start + 16 <= h <= last_ok and end_t(h) <= target * 1.25 + 1]
        if cands:
            return min(cands, key=lambda h: abs(end_t(h) - target))
        f = int(round(self.g.beat(target) - 8))
        return max(start + 16, min(f, max(start + 16, last_ok)))

    # --------------------------------------------------------------- partes
    def _opening(self, names: list[str], title: str, sub: str | None, queue: list[MediaItem], drop: int) -> int:
        opt = self.opt
        titles = names if len(names) > 1 else [title]
        conns = opt.connectors if opt.connectors is not None else default_connectors(len(titles))
        cards: list[tuple[Layout, bool]] = []
        for i, t in enumerate(titles):
            if i > 0 and i - 1 < len(conns) and conns[i - 1].strip():
                cards.append((Layout("small", conns[i - 1].strip().upper()), False))
            cards.append((Layout("big", two_lines(t)), True))
        lead = self.g.time(0)
        pre_roll = bool(opt.tagline) and lead >= 0.25
        if opt.tagline and not pre_roll:
            cards.insert(0, (Layout("small", opt.tagline.upper()), False))
        video = next((m for m in queue if m.is_video and (m.duration or 0) > 1.0), None)
        tail = (6 if video else 2) if sub else 0
        room = drop - 8 - tail
        step = 2 if len(cards) * 2 <= room else 1
        if len(cards) * step > room:
            cards = [c for c in cards if c[1]]  # sem conectores
            if len(cards) > room:
                self.notes.append("abertura reduzida: muitos capítulos para o espaço antes do drop")
                cards = cards[:max(1, room)]
        if pre_roll:
            self._put(None, Card(Layout("small", opt.tagline.upper())))
        b = 0
        for lay, push in cards:
            self._put(b if self.entries else None, Card(lay, push=push))
            b += step
        if sub:
            sub_layout = Layout("tall", two_lines(sub))
            if video:
                queue.remove(video)
                clip = self._clip(video, b, 6, max_speed=3.0)
                knock_at = b if self.entries else None
                self._put(knock_at, Knock(clip, sub_layout))
                follow = clip.start + clip.speed * self._dt(b, b + 2)
                self._put(b + 2, Clip(clip.file, round(follow, 3), clip.speed))
                b += 6
            else:
                self._put(b if self.entries else None, Card(Layout("big", two_lines(sub)), push=True))
                b += 2
        return b

    def _pre_drop(self, start: int, drop: int, queue: list[MediaItem], shown: list[str]) -> None:
        burst_at = drop - 2
        region = burst_at - start
        if region <= 0:
            return
        photos = [m for m in queue if not m.is_video]
        quick_n = min(6, region)
        calm_n = (region - quick_n) // 2
        if len(photos) >= calm_n + quick_n:
            beats = [2] * calm_n + [1] * quick_n
            if sum(beats) < region:
                beats[0] += region - sum(beats)
        elif photos:
            beats = spread(region, len(photos))
        else:
            self._put(start, Card(Layout("big", two_lines(self._title)), push=True))
            return
        b = start
        for m, n in zip(photos, beats):
            queue.remove(m)
            self._put(b, Photo(self._rel(m.path), self._motion(n)))
            shown.append(self._rel(m.path))
            self._all_shown.append(self._rel(m.path))
            b += n
        if shown:
            self._put(burst_at, Burst(tuple(shown[-8:]), 0.25))

    def _drop_pool(self, title: str, sub: str | None, tag: str | None, names: list[str]) -> list[Layout]:
        t2 = two_lines(title)
        other = names[1] if len(names) > 1 else (sub or title)
        specs = [
            f"stack x9: {title}", "blank", f"split: {t2}",
            f"grid 4x9: {tag}" if tag else f"grid 2x12: {title}",
            f"small: {other}", f"rows x5: {other}",
            f"stack x4: {tag or sub or title}", "blank", f"grid 2x12: {title}",
            f"tall: {two_lines(sub) if sub else t2}", f"rows x4: {sub or title}", f"tall: {t2}",
        ]
        return [Layout.parse(s) for s in specs]

    def _chapter_pool(self, name: str, tag: str | None) -> list[Layout]:
        n2 = two_lines(name)
        specs = [f"tall: {n2}", f"rows x5: {name}", f"stack x9: {name}",
                 f"grid 4x9: {tag}" if tag else f"grid 2x12: {name}", f"split: {n2}"]
        return [Layout.parse(s) for s in specs]

    def _units(self, items: list[MediaItem], budget: int) -> tuple[list[_Unit], list[MediaItem]]:
        units: list[_Unit] = []
        run = 0
        for m in items:
            if m.is_video:
                units.append(_Unit("video", 3, [m]))
                run = 0
            else:
                units.append(_Unit("photo", 1, [m]))
                run += 1
                if run == 3:
                    units.append(_Unit("strobe", 1))
                    run = 0
        while units and units[-1].kind == "strobe":
            units.pop()
        total = sum(u.beats for u in units)
        overflow: list[MediaItem] = []
        # encolhe: tira estrobos, encurta vídeos, junta fotos em rajadas
        while total > budget and units:
            strobes = [u for u in units if u.kind == "strobe"]
            if strobes:
                units.remove(strobes[-1])
                total -= 1
                continue
            long_videos = [u for u in units if u.kind == "video" and u.beats > 2]
            if long_videos:
                long_videos[-1].beats -= 1
                total -= 1
                continue
            merged = False
            for i in range(len(units) - 3, -1, -1):
                group = units[i:i + 4]
                if len(group) == 4 and all(u.kind == "photo" and u.beats == 1 for u in group):
                    units[i:i + 4] = [_Unit("burst", 1, [u.media[0] for u in group])]
                    total -= 3
                    merged = True
                    break
            if merged:
                continue
            last = units.pop()
            overflow.extend(last.media)
            total -= last.beats
        # estica: fotos para 2 batidas (alternando), vídeos até 4, depois fotos até 3 e 4
        for kind, cap in (("photo", 2), ("video", 4), ("photo", 3), ("photo", 4), ("video", 6)):
            if total >= budget:
                break
            pick = [u for u in units if u.kind == kind and u.beats < cap]
            for u in pick[::2] + pick[1::2]:
                if total >= budget:
                    break
                u.beats += 1
                total += 1
        if total < budget and units:
            units[-1].beats += budget - total
        return units, overflow

    @staticmethod
    def _video_before(units: list[_Unit], room: int) -> bool:
        """Há outro vídeo entre a posição atual e a subida? (para não inverter a ordem cronológica)"""
        acc = 0
        for u in units:
            if acc >= room:
                return False
            if u.kind == "video":
                return True
            acc += u.beats
        return False

    @staticmethod
    def _grow(units: list[_Unit], extra: int) -> None:
        """Distribui `extra` batidas pelas fotos (1 -> 2 batidas, alternando), senão no último item."""
        photos = [u for u in units if u.kind == "photo" and u.beats == 1]
        for u in photos[::2] + photos[1::2]:
            if extra <= 0:
                return
            u.beats += 1
            extra -= 1
        if extra > 0 and units:
            units[-1].beats += extra

    def _emit(self, u: _Unit, at: int, beats: int, pool: list[Layout], shown: list[str], hero: bool = False) -> None:
        if u.kind == "photo":
            rel = self._rel(u.media[0].path)
            self._put(at, Photo(rel, "in" if hero else self._motion(beats)))
            shown.append(rel)
            self._all_shown.append(rel)
        elif u.kind == "video":
            self._put(at, self._clip(u.media[0], at, beats))
        elif u.kind == "burst":
            files = tuple(self._rel(m.path) for m in u.media)
            self._put(at, Burst(files, beats / len(files)))
            shown.extend(files)
        else:
            self._put(at, Strobe((pool[self._pool_i % len(pool)],)))
            self._pool_i += 1

    def _chapter(self, start: int, end: int, ch: Chapter, queue: list[MediaItem], shown: list[str],
                 card: bool, tag: str | None) -> None:
        pool = self._chapter_pool(ch.name, tag)
        self._pool_i = 0
        c = start
        if card and end - start >= 6:
            self._put(c, ColorCards(Layout("tall", two_lines(ch.name))))
            c += 3
        windows: list[tuple[int, int]] = []
        for r0, h in self.a.risers:
            if r0 >= c + 2 and h + 1 <= end and (not windows or r0 >= windows[-1][1] + 2):
                windows.append((r0, h))
        blocks: list[tuple[str, int, int]] = []
        cur = c
        for r0, h in windows:
            blocks += [("free", cur, r0), ("riser", r0, h), ("hero", h, min(h + 2, end))]
            cur = min(h + 2, end)
        blocks.append(("free", cur, end))
        budget = sum(b - a for k, a, b in blocks if k in ("free", "hero"))
        units, overflow = self._units(list(queue), budget)
        queue.clear()
        last_clip_at: int | None = None
        reserved: _Unit | None = None  # vídeo longo guardado para a próxima subida
        for idx, (kind, a, b) in enumerate(blocks):
            if b <= a:
                continue
            if kind == "free":
                next_riser = blocks[idx + 1][1] if idx + 1 < len(blocks) and blocks[idx + 1][0] == "riser" else None
                pos = a
                while pos < b and units:
                    u = units.pop(0)
                    if (u.kind == "video" and reserved is None and next_riser is not None
                            and (u.media[0].duration or 0) >= 6 and next_riser - pos <= 8
                            and not self._video_before(units, next_riser - pos)):
                        reserved = u
                        self._grow(units, u.beats)
                        continue
                    n = min(u.beats, b - pos)
                    self._emit(u, pos, n, pool, shown)
                    last_clip_at = pos if u.kind == "video" else None
                    pos += n
                if pos < b:
                    recap = list(dict.fromkeys(shown[-12:]))
                    if b - pos >= 2 and len(recap) >= 3:
                        self._put(pos, Burst(tuple(recap), 0.5))
                    else:
                        self._put(pos, Strobe(tuple(pool)))
                    last_clip_at = None
            elif kind == "riser":
                if last_clip_at is not None and self._try_ramp(last_clip_at, a, b):
                    last_clip_at = None
                    continue
                long_video = reserved or next(
                    (u for u in units[:4] if u.kind == "video" and (u.media[0].duration or 0) >= 6), None)
                if long_video:
                    if long_video is not reserved:
                        units.remove(long_video)
                        self._grow(units, long_video.beats)  # as batidas que o vídeo usaria vão para as fotos
                    reserved = None
                    self._put(a, self._ramp_clip(long_video.media[0], a, b))
                    last_clip_at = None
                    continue
                files = list(dict.fromkeys(shown[-16:]))
                if len(files) < 8:  # completa com o que já passou nos capítulos anteriores
                    for f in reversed(self._all_shown):
                        if len(files) >= 8:
                            break
                        if f not in files:
                            files.insert(0, f)
                self._put(a, Burst(tuple(files), 0.25) if files else Strobe(tuple(pool)))
                last_clip_at = None
            else:  # hero
                while units and units[0].kind == "strobe":
                    units.pop(0)
                if units:
                    self._emit(units.pop(0), a, b - a, pool, shown, hero=True)
                else:
                    self._put(a, Strobe(tuple(pool)))
                last_clip_at = None
        if reserved:
            units.append(reserved)
        leftover = [m for u in units for m in u.media] + overflow
        bursts = [at for at, it in self.entries.items()
                  if isinstance(it, Burst) and at is not None and start <= at < end]
        extra = [self._rel(m.path) for m in leftover if not m.is_video]
        if extra and bursts:  # fotos que não couberam entram na última rajada do capítulo
            at = max(bursts)
            old = self.entries[at]
            span = len(old.files) * old.step
            files = old.files + tuple(extra)
            self.entries[at] = Burst(files, span / len(files))
            leftover = [m for m in leftover if m.is_video]
        if leftover:
            self.notes.append(f"{len(leftover)} arquivo(s) de {ch.name} não couberam (aumente --seconds)")

    def _ramp_clip(self, m: MediaItem, r0: int, hit: int, v0: float = 3.0, v1: float = 20.0) -> Clip:
        """Vídeo que cobre a subida inteira, começando a `v0`x e acelerando até ~`v1`x no impacto."""
        dur = m.duration or 0.0
        start = round(min(0.5, dur * 0.05), 2)
        span = self._dt(r0, hit)
        to = min(dur - 0.1, start + span * (v0 + v1) / 2)
        if to <= start + v0 * span:
            return Clip(self._rel(m.path), start, round(max(0.5, (to - start) / span), 2))
        return Clip(self._rel(m.path), start, v0, Ramp(r0, round(to, 2)))

    def _try_ramp(self, at: int, r0: int, hit: int) -> bool:
        """Se um vídeo termina onde começa a subida, estica o vídeo acelerando até o impacto."""
        clip = self.entries.get(at)
        if not isinstance(clip, Clip) or clip.file not in self._durations:
            return False
        dur = self._durations[clip.file]
        s_r = clip.start + clip.speed * self._dt(at, r0)
        need = s_r + clip.speed * self._dt(r0, hit) * 1.5
        to = min(dur - 0.1, s_r + clip.speed * self._dt(r0, hit) * 4)
        if to < need:
            return False
        self.entries[at] = Clip(clip.file, clip.start, clip.speed, Ramp(r0, round(to, 2)))
        return True

    def _final(self, hit: int, title: str, sub: str | None, tag: str | None, names: list[str]) -> int:
        t2 = two_lines(title)
        self._put(hit, ColorCards(Layout("tall", t2)))
        self._put(hit + 3, Card(Layout("tall", t2)))
        credit = f"{title} - {tag or sub}" if (tag or sub) else title
        others = [n for n in names if n != title]
        if others:
            credit += " / " + " · ".join(others)
        self._put(hit + 5, Card(Layout("small", credit)))
        return hit + 8

    # ------------------------------------------------------------------ main
    def plan(self, chapters: list[Chapter], audio: str | Path, out_dir: str | Path,
             analysis_file: str | Path | None = None) -> Storyboard:
        self._base = Path(out_dir)
        self.entries, self.notes = {}, []
        self._all_shown, self._durations, self._toggle = [], {}, False
        chs = [c for c in chapters if c.items]
        if not chs:
            raise ValueError("nenhuma mídia para montar o vídeo")
        names = [c.name.upper() for c in chs]
        title = (self.opt.title or names[0]).upper()
        self._title = title
        sub = self.opt.subtitle.upper() if self.opt.subtitle else None
        tag = self.opt.tag.upper() if self.opt.tag else None
        queues = [list(c.items) for c in chs]
        shown: list[list[str]] = [[] for _ in chs]

        drop = self._drop()
        opening_end = self._opening(names, title, sub, queues[0], drop)
        self._pre_drop(opening_end, drop, queues[0], shown[0])

        target_end = drop + 12
        near = [h for h in self.a.hits if drop + 8 <= h <= drop + 16]
        strobe_end = min(near, key=lambda h: abs(h - target_end)) if near else target_end
        self._put(drop, Strobe(tuple(self._drop_pool(title, sub, tag, names))))

        target = self.opt.seconds or min(90.0, max(20.0, self._natural_seconds(queues, strobe_end)))
        final = self._final_hit(strobe_end, target)
        body_end = final
        riser = self.a.riser_into(final)
        if riser and riser[0] >= strobe_end + 8:
            body_end = riser[0]
            specs = [f"stack x9: {title}"] + [f"rows x5: {n}" for n in names[1:3]] + \
                    [f"tall: {two_lines(sub) if sub else two_lines(title)}"]
            self._put(body_end, Strobe(tuple(Layout.parse(s) for s in specs)))

        # corpo: divide o espaço entre os capítulos pelo "peso" da mídia que sobrou
        weights = [sum(3 if m.is_video else 1.33 for m in q) + (3 if i and q else 0) for i, q in enumerate(queues)]
        active = [i for i, w in enumerate(weights) if w > 0]
        span = body_end - strobe_end
        bounds = [strobe_end]
        acc = 0.0
        total_w = sum(weights[i] for i in active) or 1.0
        for i in active[:-1]:
            acc += weights[i]
            raw = strobe_end + span * acc / total_w
            near = [h for h in self.a.hits if abs(h - raw) <= 4 and bounds[-1] + 4 <= h <= body_end - 4]
            major = [h for h in near if h in self.a.major_hits]
            pick = min(major or near, key=lambda h: abs(h - raw)) if (major or near) else int(round(raw))
            bounds.append(max(bounds[-1] + 4, min(pick, body_end - 4)))
        bounds.append(body_end)
        for k, i in enumerate(active):
            self._chapter(bounds[k], bounds[k + 1], chs[i], queues[i], shown[i], card=i > 0, tag=tag)
        if not active and span > 0:
            self._put(strobe_end, Strobe(tuple(self._drop_pool(title, sub, tag, names))))

        end = self._final(final, title, sub, tag, names)
        entries = [Entry(at, it) for at, it in sorted(self.entries.items(), key=lambda kv: -1e9 if kv[0] is None
                                                       else kv[0])]
        seconds = self.g.time(end)
        header = [
            "Roteiro gerado pelo reelbeat. Edite à vontade e rode: reelbeat render <este arquivo>",
            f"Música: {self.g.bpm:.1f} BPM · drop na batida {drop} · final na batida {final} · {seconds:.1f} s",
            "'at' é a batida em que cada item entra; ele dura até o próximo item.",
        ] + [f"Aviso: {n}" for n in self.notes]
        return Storyboard(
            audio=self._rel(audio),
            entries=entries,
            end=end,
            width=self.opt.width,
            height=self.opt.height,
            fps=self.opt.fps,
            analysis=self._rel(analysis_file) if analysis_file else None,
            notes=header,
        )

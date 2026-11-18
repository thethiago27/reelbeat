"""Roteiro em YAML: fácil de ler e de editar à mão.

Exemplo::

    reelbeat: 1
    audio: musica.mp3
    analysis: musica.beats.json
    end: 148
    timeline:
      - at: start
        text: "small: UMA VIAGEM POR"
      - at: 0
        title: "big: PORTO / SEGURO"
      - at: 16
        photo: fotos/IMG_0436.jpg
        motion: in
      - at: 32
        strobe: ["stack x9: PORTO SEGURO", blank, "tall: BAHIA"]
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from ..domain import Burst, Card, Clip, ColorCards, Entry, Knock, Layout, Photo, Ramp, Storyboard, Strobe

FORMAT_VERSION = 1
_ITEM_KEYS = ("text", "title", "photo", "clip", "knock", "burst", "strobe", "colors")


def _num(v: Any) -> float | int:
    f = float(v)
    return int(f) if f.is_integer() else round(f, 4)


# ---------------------------------------------------------------- leitura
def _clip_from(d: dict, file_key: str = "clip") -> Clip:
    ramp = d.get("ramp")
    return Clip(
        file=str(d[file_key]),
        start=float(d.get("start", 0.0)),
        speed=float(d.get("speed", 1.0)),
        ramp=Ramp(float(ramp["at"]), float(ramp["to"])) if ramp else None,
    )


def _entry_from(d: dict) -> Entry:
    if "at" not in d:
        raise ValueError(f"item sem 'at': {d}")
    at = None if d["at"] in ("start", None) else float(d["at"])
    keys = [k for k in _ITEM_KEYS if k in d]
    if len(keys) != 1:
        raise ValueError(f"cada item precisa de exatamente um tipo ({', '.join(_ITEM_KEYS)}): {d}")
    kind = keys[0]
    v = d[kind]
    if kind in ("text", "title"):
        item: Any = Card(
            Layout.parse(v), bg=d.get("bg", "black"), fg=d.get("fg"), push=bool(d.get("push", kind == "title"))
        )
    elif kind == "photo":
        item = Photo(str(v), d.get("motion", "punch"))
    elif kind == "clip":
        item = _clip_from(d)
    elif kind == "knock":
        if not isinstance(v, dict) or "layout" not in v:
            raise ValueError("knock precisa de {clip: arquivo, layout: ...}")
        item = Knock(_clip_from(v), Layout.parse(v["layout"]))
    elif kind == "burst":
        item = Burst(tuple(str(f) for f in v), float(d.get("step", 0.25)))
    elif kind == "strobe":
        item = Strobe(tuple(Layout.parse(s) for s in v), float(d.get("step", 1.0)))
    else:
        if "layout" not in d:
            raise ValueError("colors precisa de 'layout'")
        item = ColorCards(Layout.parse(d["layout"]), tuple(v), float(d.get("step", 1.0)))
    return Entry(at, item)


def load_storyboard(path: str | Path) -> Storyboard:
    path = Path(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "timeline" not in data:
        raise ValueError(f"{path} não parece um roteiro do reelbeat (falta 'timeline')")
    size = data.get("size", [1080, 1920])
    return Storyboard(
        audio=str(data["audio"]),
        entries=[_entry_from(e) for e in data["timeline"]],
        end=float(data["end"]),
        audio_start=float(data.get("audio_start", 0.0)),
        width=int(size[0]),
        height=int(size[1]),
        fps=int(data.get("fps", 30)),
        fade_out=float(data.get("fade_out", 0.9)),
        analysis=data.get("analysis"),
    )


# ---------------------------------------------------------------- escrita
def _clip_to(c: Clip, file_key: str = "clip") -> dict:
    d: dict[str, Any] = {file_key: c.file, "start": _num(c.start), "speed": _num(c.speed)}
    if c.ramp:
        d["ramp"] = {"at": _num(c.ramp.at), "to": _num(c.ramp.to)}
    return d


def _entry_to(e: Entry) -> dict:
    d: dict[str, Any] = {"at": "start" if e.at is None else _num(e.at)}
    it = e.item
    if isinstance(it, Card):
        d["title" if it.push else "text"] = str(it.layout)
        if it.bg != "black":
            d["bg"] = it.bg
        if it.fg:
            d["fg"] = it.fg
    elif isinstance(it, Photo):
        d["photo"] = it.file
        if it.motion != "punch":
            d["motion"] = it.motion
    elif isinstance(it, Clip):
        d.update(_clip_to(it))
    elif isinstance(it, Knock):
        d["knock"] = {**_clip_to(it.clip), "layout": str(it.layout)}
    elif isinstance(it, Burst):
        d["burst"] = list(it.files)
        d["step"] = _num(it.step)
    elif isinstance(it, Strobe):
        d["strobe"] = [str(lay) for lay in it.layouts]
        if it.step != 1:
            d["step"] = _num(it.step)
    elif isinstance(it, ColorCards):
        d["colors"] = list(it.colors)
        d["layout"] = str(it.layout)
        if it.step != 1:
            d["step"] = _num(it.step)
    return d


def storyboard_to_dict(sb: Storyboard) -> dict:
    out: dict[str, Any] = {"reelbeat": FORMAT_VERSION, "audio": sb.audio}
    if sb.audio_start:
        out["audio_start"] = _num(sb.audio_start)
    if sb.analysis:
        out["analysis"] = sb.analysis
    out.update({"size": [sb.width, sb.height], "fps": sb.fps, "end": _num(sb.end), "fade_out": _num(sb.fade_out)})
    out["timeline"] = [_entry_to(e) for e in sb.entries]
    return out


class _Dumper(yaml.SafeDumper):
    pass


def _flow_short_lists(dumper: yaml.SafeDumper, data: list) -> yaml.Node:
    flow = all(isinstance(x, (int, float, str)) and len(str(x)) < 40 for x in data) and len(data) <= 6
    return dumper.represent_sequence("tag:yaml.org,2002:seq", data, flow_style=flow)


_Dumper.add_representer(list, _flow_short_lists)


def dump_storyboard(sb: Storyboard, path: str | Path) -> Path:
    path = Path(path)
    header = "".join(f"# {n}\n" for n in sb.notes)
    body = yaml.dump(storyboard_to_dict(sb), Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=120)
    path.write_text(header + body, encoding="utf-8")
    return path

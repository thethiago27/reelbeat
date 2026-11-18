"""Linha de comando do reelbeat.

    reelbeat auto musica.mp3 midia/ --subtitle BAHIA --tag BA --render
    reelbeat render roteiro.yaml
    reelbeat preview roteiro.yaml
    reelbeat analyze musica.mp3
    reelbeat cards BA
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import time
from pathlib import Path

from . import __version__


def _progress(label: str):
    start = time.time()

    def show(i: int, n: int, *extra) -> None:
        pct = 100 * i / max(n, 1)
        sys.stderr.write(f"\r{label}: {i}/{n} ({pct:3.0f}%) {time.time() - start:5.1f}s ")
        if i >= n:
            sys.stderr.write("\n")
        sys.stderr.flush()

    return show


def _size(text: str) -> tuple[int, int]:
    w, _, h = text.lower().partition("x")
    w, h = int(w), int(h)
    if w % 2 or h % 2:
        raise argparse.ArgumentTypeError("largura e altura precisam ser pares (ex.: 1080x1920)")
    return w, h


def _csv(text: str) -> list[str]:
    return [p.strip() for p in text.split(",")]


def _load_or_analyze(audio: Path, cache: Path, duration: float | None = None):
    from .analysis import analyze
    from .io import load_analysis, save_analysis

    if cache.exists() and cache.stat().st_mtime >= audio.stat().st_mtime:
        return load_analysis(cache)
    print(f"analisando {audio.name}...", file=sys.stderr)
    result = analyze(str(audio), duration=duration)
    save_analysis(result, cache)
    return result


# ------------------------------------------------------------------ comandos
def cmd_analyze(args) -> int:
    from .analysis import analyze
    from .io import save_analysis

    audio = Path(args.audio)
    out = Path(args.output) if args.output else audio.with_suffix(".beats.json")
    a = analyze(str(audio), duration=args.duration)
    save_analysis(a, out)
    t = a.grid.time
    print(f"{a.grid.bpm:.1f} BPM · {len(a.grid)} batidas · {a.duration:.1f} s")
    if a.drop is not None:
        print(f"drop: batida {a.drop} ({t(a.drop):.2f} s)")
    print("subidas -> impacto: " + ", ".join(f"{r0}->{h} ({t(h):.1f}s)" for r0, h in a.risers[:20]))
    print(f"análise salva em {out}")
    return 0


def cmd_auto(args) -> int:
    from .io import dump_storyboard
    from .media import scan
    from .planner import AutoPlanner, PlanOptions

    audio, media = Path(args.audio), Path(args.media)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    cache = out.parent / f"{audio.stem}.beats.json"
    analysis = _load_or_analyze(audio, cache, args.duration)
    chapters = scan(media, _csv(args.names) if args.names else None)
    width, height = args.size
    opts = PlanOptions(
        title=args.title,
        subtitle=args.subtitle,
        tag=args.tag,
        tagline=None if args.no_tagline else args.tagline,
        connectors=_csv(args.connectors) if args.connectors is not None else None,
        seconds=args.seconds,
        width=width,
        height=height,
        fps=args.fps,
    )
    sb = AutoPlanner(analysis, opts).plan(chapters, audio, out.parent, cache)
    dump_storyboard(sb, out)
    count = sum(len(c.items) for c in chapters)
    seconds = analysis.grid.time(sb.end)
    print(f"{len(chapters)} capítulo(s), {count} arquivo(s) -> roteiro de {seconds:.1f} s em {out}")
    for note in sb.notes[3:]:
        print(note)
    if args.render:
        return _render(out, Path(args.render) if isinstance(args.render, str) else out.with_suffix(".mp4"),
                       args.crf, args.silent)
    return 0


def _compositor(storyboard_path: Path):
    from .io import load_storyboard
    from .render import Compositor

    sb = load_storyboard(storyboard_path)
    base = storyboard_path.parent
    audio = base / sb.audio
    cache = base / sb.analysis if sb.analysis else base / f"{Path(sb.audio).stem}.beats.json"
    analysis = _load_or_analyze(audio, cache)
    return Compositor(sb, analysis.grid, base, base / ".reelbeat-cache"), audio


def _render(storyboard_path: Path, out: Path, crf: int, silent: bool) -> int:
    from .render import encode_video, mux_audio

    comp, audio = _compositor(storyboard_path)
    comp.prepare(_progress("preparando vídeos"))
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        silent_path = out.with_name(out.stem + "_sem_audio.mp4") if silent else Path(tmp) / "video.mp4"
        encode_video(comp, silent_path, crf=crf, progress=_progress("renderizando"))
        mux_audio(silent_path, audio, out, comp.sb.audio_start, comp.duration, comp.sb.fade_out)
    print(f"pronto: {out} ({comp.duration:.1f} s)")
    if silent:
        print(f"sem áudio: {silent_path}")
    return 0


def cmd_render(args) -> int:
    path = Path(args.storyboard)
    out = Path(args.output) if args.output else path.with_suffix(".mp4")
    return _render(path, out, args.crf, args.silent)


def cmd_preview(args) -> int:
    from PIL import Image

    from .render import contact_sheet

    path = Path(args.storyboard)
    comp, _ = _compositor(path)
    comp.prepare(_progress("preparando vídeos"))
    sheet = contact_sheet(comp, args.start, args.end, args.every, args.thumb)
    out = Path(args.output) if args.output else path.with_suffix(".png")
    Image.fromarray(sheet).save(out)
    print(f"prévia: {out}")
    return 0


def cmd_cards(args) -> int:
    from .render import export_cards

    files = export_cards(args.text, Path(args.output), layout=args.layout, width=args.size[0], height=args.size[1])
    for f in files:
        print(f)
    return 0


# --------------------------------------------------------------------- parser
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="reelbeat", description="Vídeos verticais cortados na batida da música.")
    p.add_argument("--version", action="version", version=f"reelbeat {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    a = sub.add_parser("analyze", help="mostra BPM, drop, subidas e impactos da música")
    a.add_argument("audio")
    a.add_argument("-o", "--output", help="arquivo .json da análise (padrão: <musica>.beats.json)")
    a.add_argument("--duration", type=float, help="analisa só os primeiros N segundos")
    a.set_defaults(func=cmd_analyze)

    au = sub.add_parser("auto", help="monta o roteiro automaticamente a partir da música e da pasta de mídia")
    au.add_argument("audio", help="arquivo de música (mp3, m4a, wav...)")
    au.add_argument("media", help="pasta de fotos/vídeos (subpastas = capítulos)")
    au.add_argument("-o", "--output", default="roteiro.yaml", help="roteiro gerado (padrão: roteiro.yaml)")
    au.add_argument("--title", help="título geral do vídeo (padrão: nome do 1º capítulo)")
    au.add_argument("--subtitle", help="subtítulo, ex.: BAHIA")
    au.add_argument("--tag", help="sigla curta para os mosaicos, ex.: BA")
    au.add_argument("--tagline", default="UMA VIAGEM POR", help="texto pequeno que abre o vídeo")
    au.add_argument("--no-tagline", action="store_true", help="começa direto no primeiro título")
    au.add_argument("--connectors", help='textinhos entre os títulos, separados por vírgula: "COM PARADA EM,E"')
    au.add_argument("--names", help='nomes dos capítulos, separados por vírgula: "PORTO SEGURO,ARRAIAL D\'AJUDA"')
    au.add_argument("--seconds", type=float, help="duração alvo (padrão: pela quantidade de mídia)")
    au.add_argument("--duration", type=float, help="analisa só os primeiros N segundos da música")
    au.add_argument("--size", type=_size, default=(1080, 1920), help="largura x altura (padrão 1080x1920)")
    au.add_argument("--fps", type=int, default=30)
    au.add_argument("--render", nargs="?", const=True, help="já renderiza o vídeo (opcional: arquivo de saída)")
    au.add_argument("--crf", type=int, default=22, help="qualidade do H.264 (menor = melhor; padrão 22)")
    au.add_argument("--silent", action="store_true", help="salva também uma versão sem áudio")
    au.set_defaults(func=cmd_auto)

    r = sub.add_parser("render", help="renderiza o vídeo a partir de um roteiro")
    r.add_argument("storyboard")
    r.add_argument("-o", "--output", help="vídeo de saída (padrão: <roteiro>.mp4)")
    r.add_argument("--crf", type=int, default=22, help="qualidade do H.264 (menor = melhor; padrão 22)")
    r.add_argument("--silent", action="store_true", help="salva também uma versão sem áudio")
    r.set_defaults(func=cmd_render)

    pv = sub.add_parser("preview", help="folha de contato do roteiro, sem renderizar o vídeo")
    pv.add_argument("storyboard")
    pv.add_argument("-o", "--output", help="imagem de saída (padrão: <roteiro>.png)")
    pv.add_argument("--every", type=float, default=0.25, help="um quadro a cada N segundos")
    pv.add_argument("--start", type=float, default=0.0)
    pv.add_argument("--end", type=float)
    pv.add_argument("--thumb", type=int, default=108, help="largura de cada miniatura")
    pv.set_defaults(func=cmd_preview)

    c = sub.add_parser("cards", help="exporta cartelas PNG de um texto em vermelho, verde, azul, preto e branco")
    c.add_argument("text")
    c.add_argument("-o", "--output", default="cartelas")
    c.add_argument("--layout", default="big", choices=["big", "tall", "small"])
    c.add_argument("--size", type=_size, default=(1080, 1920))
    c.set_defaults(func=cmd_cards)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

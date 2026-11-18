from pathlib import Path

from reelbeat.domain import Burst, Card, Clip, ColorCards, Knock, Photo, Strobe, expand
from reelbeat.io import dump_storyboard, load_storyboard
from reelbeat.media import Chapter, MediaItem, chapter_name, scan
from reelbeat.planner import AutoPlanner, PlanOptions
from reelbeat.planner.auto import default_connectors, spread


def test_chapter_names_from_folders(media_dir):
    chapters = scan(media_dir)
    assert [c.name for c in chapters] == ["PORTO SEGURO", "ARRAIAL DAJUDA", "TRANCOSO"]
    assert chapter_name("02-arraial_dajuda") == "ARRAIAL DAJUDA"
    named = scan(media_dir, ["Porto Seguro", "Arraial d'Ajuda", "Trancoso"])
    assert named[1].name == "ARRAIAL D'AJUDA"


def test_helpers():
    assert spread(7, 3) == [3, 2, 2]
    assert default_connectors(3) == ["COM PARADA EM", "E"]
    assert default_connectors(1) == []


def _plan(analysis, media_dir, tmp_path, **opts):
    chapters = scan(media_dir, ["PORTO SEGURO", "ARRAIAL D'AJUDA", "TRANCOSO"])
    planner = AutoPlanner(analysis, PlanOptions(subtitle="Bahia", tag="BA", **opts))
    return planner.plan(chapters, tmp_path / "musica.mp3", tmp_path, tmp_path / "musica.beats.json"), chapters


def test_plan_structure(analysis, media_dir, tmp_path):
    sb, chapters = _plan(analysis, media_dir, tmp_path)
    segs = expand(sb, analysis.grid)  # contínuo e válido
    assert segs[0].t0 == 0.0
    items = {e.at: e.item for e in sb.entries}
    # abertura: títulos dos três lugares e subtítulo
    titles = [it.layout.text for it in items.values() if isinstance(it, Card) and it.push]
    assert titles[:3] == ["PORTO / SEGURO", "ARRAIAL / D'AJUDA", "TRAN / COSO"]
    # drop em estrobo
    assert isinstance(items[32], Strobe)
    # cartelas RGB dos capítulos 2 e 3 + final
    cards = [it.layout.text for it in items.values() if isinstance(it, ColorCards)]
    assert cards == ["ARRAIAL / D'AJUDA", "TRAN / COSO", "PORTO / SEGURO"]
    # o final cai num impacto que vem depois de uma subida
    final_at = max(at for at, it in items.items() if isinstance(it, ColorCards))
    assert final_at in analysis.major_hits
    assert sb.end == final_at + 8
    # crédito
    assert any(isinstance(it, Card) and "PORTO SEGURO - BA" in it.layout.text for it in items.values())


def test_every_photo_is_used(analysis, media_dir, tmp_path):
    sb, chapters = _plan(analysis, media_dir, tmp_path)
    used = set()
    for e in sb.entries:
        if isinstance(e.item, Photo):
            used.add(Path(e.item.file).name)
        elif isinstance(e.item, Burst):
            used.update(Path(f).name for f in e.item.files)
    expected = {i.path.name for c in chapters for i in c.items}
    assert expected <= used


def test_paths_are_relative_and_roundtrip(analysis, media_dir, tmp_path):
    sb, _ = _plan(analysis, media_dir, tmp_path)
    photo = next(e.item for e in sb.entries if isinstance(e.item, Photo))
    assert photo.file.startswith("midia/")
    assert sb.audio == "musica.mp3"
    back = load_storyboard(dump_storyboard(sb, tmp_path / "roteiro.yaml"))
    assert back.entries == sb.entries


def test_videos_become_knock_and_ramps(analysis, tmp_path):
    a = tmp_path / "a"
    photos = [MediaItem(a / f"p{i}.jpg", "photo") for i in range(12)]
    sea = MediaItem(a / "mar.mov", "video", duration=12.0)
    walk = MediaItem(a / "caminhada.mov", "video", duration=37.0)
    ch1 = Chapter("PORTO SEGURO", [sea] + photos[:8])
    ch2 = Chapter("TRANCOSO", photos[8:10] + [walk] + photos[10:])
    sb = AutoPlanner(analysis, PlanOptions(subtitle="BAHIA", seconds=60)).plan([ch1, ch2], tmp_path / "m.mp3", tmp_path)
    expand(sb, analysis.grid)
    knocks = [e for e in sb.entries if isinstance(e.item, Knock)]
    assert knocks and knocks[0].item.clip.file.endswith("mar.mov")
    walk_clip = next(e for e in sb.entries if isinstance(e.item, Clip) and e.item.file.endswith("caminhada.mov"))
    assert walk_clip.item.ramp is not None  # a caminhada acelera até um impacto
    assert walk_clip.item.ramp.to <= 37.0


def test_target_seconds_controls_length(analysis, media_dir, tmp_path):
    short, _ = _plan(analysis, media_dir, tmp_path, seconds=30)
    long, _ = _plan(analysis, media_dir, tmp_path, seconds=70)
    assert analysis.grid.time(short.end) < analysis.grid.time(long.end)

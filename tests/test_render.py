import numpy as np
import pytest

from reelbeat.cli import main
from reelbeat.domain import Burst, Card, Entry, Layout, Photo, Storyboard, Strobe
from reelbeat.domain.layout import LAYOUT_TYPES
from reelbeat.render import Compositor, Typesetter, contact_sheet, encode_video
from tests.conftest import HAS_FFMPEG, make_photo

W, H = 216, 384


@pytest.mark.parametrize("kind", [t for t in LAYOUT_TYPES if t != "blank"])
def test_every_layout_draws_something(kind):
    ts = Typesetter(W, H)
    extra = {"stack": " x3", "rows": " x3", "grid": " 2x3"}.get(kind, "")
    mask = ts.mask(f"{kind}{extra}: PORTO / SEGURO")
    assert mask.shape == (H, W)
    assert mask.max() > 0.9


def test_big_titles_share_letter_height():
    ts = Typesetter(1080, 1920)
    heights = []
    for text in ("PORTO / SEGURO", "TRAN / COSO"):
        rows = np.where(ts.mask(f"big: {text}").max(axis=1) > 0.5)[0]
        heights.append(rows[-1] - rows[0])
    assert abs(heights[0] - heights[1]) / heights[0] < 0.08


@pytest.fixture
def small_storyboard(tmp_path):
    make_photo(tmp_path / "a.jpg", (250, 20, 20))
    make_photo(tmp_path / "b.jpg", (20, 20, 250), size=(500, 300))
    sb = Storyboard(
        audio="musica.mp3", end=8, width=W, height=H, fps=10,
        entries=[
            Entry(None, Card(Layout.parse("small: OI"))),
            Entry(0, Card(Layout.parse("big: PORTO / SEGURO"), push=True)),
            Entry(2, Photo("a.jpg", "in")),
            Entry(4, Burst(("a.jpg", "b.jpg"), 0.25)),
            Entry(5, Strobe((Layout.parse("tall: BAHIA"),))),
            Entry(6, Card(Layout.parse("tall: FIM"), bg="red")),
        ],
    )
    return sb, tmp_path


def test_compositor_frames(small_storyboard, grid):
    sb, base = small_storyboard
    comp = Compositor(sb, grid, base, base / ".cache")
    comp.prepare()
    for t in np.arange(0, comp.duration, 0.1):
        f = comp.frame(float(t))
        assert f.shape == (H, W, 3) and f.dtype == np.uint8
    photo = comp.frame(grid.time(2.5))
    assert photo[..., 0].mean() > 200  # foto vermelha
    card = comp.frame(grid.time(7))
    assert tuple(card[0, 0]) == (255, 0, 0)  # fundo vermelho da cartela
    sheet = contact_sheet(comp, every=0.5, thumb_width=54, cols=8)
    assert sheet.ndim == 3


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg não instalado")
def test_encode(small_storyboard, grid, tmp_path):
    sb, base = small_storyboard
    comp = Compositor(sb, grid, base, base / ".cache")
    out = encode_video(comp, tmp_path / "v.mp4")
    assert out.exists() and out.stat().st_size > 1000


def test_cards_command(tmp_path):
    assert main(["cards", "BA", "-o", str(tmp_path / "cartelas"), "--size", "108x192"]) == 0
    names = sorted(p.name for p in (tmp_path / "cartelas").glob("*.png"))
    assert names == ["BA_azul.png", "BA_branco.png", "BA_preto.png", "BA_verde.png", "BA_vermelho.png"]


def test_cli_reports_missing_media(tmp_path, capsys):
    code = main(["render", str(tmp_path / "nao-existe.yaml")])
    assert code == 1
    assert "erro" in capsys.readouterr().err

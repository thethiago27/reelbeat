import pytest

from reelbeat.domain import (
    BeatGrid,
    Burst,
    Card,
    ColorCards,
    Entry,
    Layout,
    Photo,
    Storyboard,
    Strobe,
    expand,
)
from reelbeat.domain.layout import two_lines
from reelbeat.domain.storyboard import StrobeBeat


class TestBeatGrid:
    def test_interpolates_and_extrapolates(self):
        g = BeatGrid((1.0, 1.5, 2.0, 2.5))
        assert g.time(0) == 1.0
        assert g.time(1.5) == pytest.approx(1.75)
        assert g.time(-2) == pytest.approx(0.0)
        assert g.time(5) == pytest.approx(3.5)
        assert g.bpm == pytest.approx(120)

    def test_beat_is_inverse_of_time(self):
        g = BeatGrid.regular(140, 50, offset=0.3)
        for b in (-1.5, 0, 3.25, 48.5, 60):
            assert g.beat(g.time(b)) == pytest.approx(b)

    def test_rejects_unsorted(self):
        with pytest.raises(ValueError):
            BeatGrid((1.0, 0.5))


class TestLayout:
    @pytest.mark.parametrize(
        "spec",
        ["small: UMA VIAGEM POR", "big: PORTO / SEGURO", "tall: BAHIA", "stack x9: PORTO SEGURO",
         "split: TRAN / COSO", "grid 4x9: BA", "rows x5: ARRAIAL D'AJUDA", "blank"],
    )
    def test_roundtrip(self, spec):
        assert str(Layout.parse(spec)) == spec

    def test_defaults_and_lines(self):
        lay = Layout.parse("stack: OI")
        assert lay.n == 4
        assert Layout.parse("big: PORTO / SEGURO").lines == ["PORTO", "SEGURO"]

    def test_invalid(self):
        with pytest.raises(ValueError):
            Layout.parse("huge: X")
        with pytest.raises(ValueError):
            Layout.parse("big:")

    @pytest.mark.parametrize(
        "name,expected",
        [("PORTO SEGURO", "PORTO / SEGURO"), ("TRANCOSO", "TRAN / COSO"), ("BAHIA", "BAHIA"),
         ("ARRAIAL D'AJUDA", "ARRAIAL / D'AJUDA")],
    )
    def test_two_lines(self, name, expected):
        assert two_lines(name) == expected


class TestExpand:
    def _sb(self, entries, end=12):
        return Storyboard(audio="m.mp3", entries=entries, end=end)

    def test_segments_are_contiguous(self, grid):
        sb = self._sb([
            Entry(None, Card(Layout.parse("small: OI"))),
            Entry(0, Photo("a.jpg")),
            Entry(2, Burst(("a.jpg", "b.jpg"), 0.25)),
            Entry(4, Strobe((Layout.parse("tall: X"), Layout.parse("blank")))),
            Entry(8, ColorCards(Layout.parse("tall: FIM"))),
        ])
        segs = expand(sb, grid)
        assert segs[0].t0 == 0.0
        for a, b in zip(segs, segs[1:]):
            assert a.t1 == pytest.approx(b.t0)
        assert segs[-1].t1 == pytest.approx(grid.time(12))
        assert sum(isinstance(s.item, Photo) and s.item.motion == "still" for s in segs) == 8
        assert sum(isinstance(s.item, StrobeBeat) for s in segs) == 4
        assert [s.item.bg for s in segs if isinstance(s.item, Card) and s.item.layout.text == "FIM"] == \
               ["red", "green", "blue", "red"]

    def test_rejects_duplicate_beats(self, grid):
        with pytest.raises(ValueError):
            expand(self._sb([Entry(None, Photo("a.jpg")), Entry(2, Photo("b.jpg")), Entry(2, Photo("c.jpg"))]), grid)

    def test_rejects_bad_motion_and_color(self):
        with pytest.raises(ValueError):
            Photo("a.jpg", "spin")
        with pytest.raises(ValueError):
            Card(Layout.parse("blank"), bg="purple")

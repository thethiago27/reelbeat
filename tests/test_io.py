from reelbeat.domain import Card, Clip, Entry, Knock, Layout, Photo, Ramp, Storyboard, Strobe, TrackAnalysis
from reelbeat.io import dump_storyboard, load_analysis, load_storyboard, save_analysis


def test_storyboard_yaml_roundtrip(tmp_path):
    sb = Storyboard(
        audio="musica.mp3",
        analysis="musica.beats.json",
        end=40,
        entries=[
            Entry(None, Card(Layout.parse("small: UMA VIAGEM POR"))),
            Entry(0, Card(Layout.parse("big: PORTO / SEGURO"), push=True)),
            Entry(2, Knock(Clip("mar.mov", 0.5, 3), Layout.parse("tall: BAHIA"))),
            Entry(4, Photo("a.jpg", "in")),
            Entry(6, Clip("caminhada.mov", 0, 3, Ramp(8, 20.5))),
            Entry(10, Strobe((Layout.parse("stack x9: PORTO SEGURO"), Layout.parse("blank")))),
            Entry(12, Card(Layout.parse("tall: FIM"), bg="red")),
        ],
        notes=["comentário de teste"],
    )
    path = dump_storyboard(sb, tmp_path / "roteiro.yaml")
    text = path.read_text(encoding="utf-8")
    assert text.startswith("# comentário de teste")
    back = load_storyboard(path)
    assert back.entries == sb.entries
    assert back.end == 40 and back.audio == "musica.mp3" and back.analysis == "musica.beats.json"


def test_analysis_json_roundtrip(tmp_path, analysis: TrackAnalysis):
    path = save_analysis(analysis, tmp_path / "a.json")
    back = load_analysis(path)
    assert back.hits == analysis.hits
    assert back.risers == analysis.risers
    assert back.drop == 32
    assert back.grid.times == analysis.grid.times

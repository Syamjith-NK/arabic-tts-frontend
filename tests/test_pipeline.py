"""The front-end as a caller uses it."""
import json

import pytest

from arabic_tts_frontend import Lexicon, VoiceFrontEnd
from arabic_tts_frontend.cli import main


def test_prepare_returns_both_forms():
    fe = VoiceFrontEnd()
    p = fe.prepare("في عام ٢٠٢٦ ارتفعت النسبة إلى ٤٧%.")
    assert p.original == "في عام ٢٠٢٦ ارتفعت النسبة إلى ٤٧%."
    assert p.spoken == "في عام ألفان وستة وعشرون ارتفعت النسبة إلى سبعة وأربعون بالمئة."
    assert p.changed


def test_diacritisation_is_off_without_a_lexicon():
    fe = VoiceFrontEnd()
    assert fe.dia is None
    assert fe.diacritics_licence.startswith("n/a")
    assert fe.prepare("مرحبا").coverage == 1.0


def test_a_custom_lexicon_reaches_the_pipeline():
    fe = VoiceFrontEnd(lexicon=Lexicon.builtin().update({"ADNOC": "أدنوك"}))
    assert "أدنوك" in fe.prepare("شركة ADNOC").spoken


def test_diacritiser_reports_its_own_licence(tmp_path):
    lex = tmp_path / "lex.json"
    lex.write_text(json.dumps({
        "meta": {"licence": "GPL-2.0 (derived from Tashkeela)"},
        "words": {"كتب": ["كَتَبَ", 12, 3], "مرحبا": ["مَرْحَبًا", 5, 1]},
    }, ensure_ascii=False), encoding="utf-8")
    fe = VoiceFrontEnd(diacritics_lexicon=lex)
    # The lexicon's licence, NOT the engine's. A copyleft lexicon cannot go into
    # a proprietary product and the caller has to be able to find that out.
    assert fe.diacritics_licence == "GPL-2.0 (derived from Tashkeela)"

    p = fe.prepare("مرحبا كتب")
    assert "مَرْحَبًا" in p.spoken
    # كتب has three attested forms: flagged for review rather than silently guessed.
    assert [w.surface for w in p.uncertain] == ["كتب"]
    assert p.coverage == 0.5
    assert "review" in p.report()


def test_unknown_words_pass_through_bare(tmp_path):
    lex = tmp_path / "lex.json"
    lex.write_text(json.dumps({"meta": {}, "words": {}}, ensure_ascii=False), encoding="utf-8")
    fe = VoiceFrontEnd(diacritics_lexicon=lex)
    p = fe.prepare("كلمة غريبة")
    assert p.spoken == "كلمة غريبة"
    assert len(p.uncertain) == 2


@pytest.mark.parametrize("argv,expected", [
    (["موعدنا 08:30"], "موعدنا الثامنة والنصف"),
    (["النمو", "25%"], "النمو خمسة وعشرون بالمئة"),
])
def test_cli_prints_the_spoken_form(capsys, argv, expected):
    assert main(argv) == 0
    assert capsys.readouterr().out.strip() == expected


def test_cli_json_reports_the_rules_that_fired(capsys):
    main(["--json", "في عام ٢٠٢٦"])
    out = json.loads(capsys.readouterr().out)
    assert out["original"] == "في عام ٢٠٢٦"
    assert out["applied"] == ["fold_digits", "cardinal"]


def test_cli_reads_stdin(capsys, monkeypatch):
    import io
    monkeypatch.setattr("sys.stdin", io.StringIO("النمو 25%\n\nموعدنا 08:30\n"))
    main([])
    assert capsys.readouterr().out.splitlines() == [
        "النمو خمسة وعشرون بالمئة", "", "موعدنا الثامنة والنصف"]

"""The pronunciation lexicon.

Almost all of the risk here is boundary handling: a substring match turns `كم`
inside `تراكم` into `تراكميلومتر`, which is worse than not converting at all.
"""
import json

import pytest

from arabic_tts_frontend import Lexicon, normalise


@pytest.fixture
def lex():
    return Lexicon.builtin()


def test_builtin_is_mit_and_says_so(lex):
    assert lex.licence == "MIT"
    assert len(lex.entries) > 50


@pytest.mark.parametrize("text,expected", [
    ("المسافة 12 km", "المسافة 12 كيلومتر"),
    ("المساحة 5 km²", "المساحة 5 كيلومتر مربع"),
    # Longest key first, or `km` eats the start of `km/h`.
    ("السرعة 100 km/h", "السرعة 100 كيلومتر في الساعة"),
    ("رصيد 500 AED", "رصيد 500 درهم"),
    ("مدير AI", "مدير الذكاء الاصطناعي"),
    ("ص.ب 1234", "صندوق بريد 1234"),
])
def test_known_tokens_are_rewritten(lex, text, expected):
    assert lex.apply(text) == expected


@pytest.mark.parametrize("text", [
    "تراكم الثلوج",      # كم inside an Arabic word
    "AIRPORT مفتوح",     # AI at the start of a Latin word
    "رسالة SMSك",        # Latin key followed by an Arabic letter - \b does not fire here
])
def test_a_key_inside_a_longer_word_is_left_alone(lex, text):
    assert lex.apply(text) == text


def test_a_digit_beside_a_unit_is_normal_writing(lex):
    # A LETTER boundary, not a word boundary: 12km must still convert.
    assert lex.apply("12km") == "12 كيلومتر"


def test_symbols_need_no_boundary(lex):
    # Demanding one meant ٢٥٪ never matched, because the digit tripped the lookbehind.
    assert lex.apply("25%").strip() == "25 بالمئة"
    assert lex.apply("40°C").strip() == "40 درجة مئوية"


def test_caller_entries_override_the_builtins(lex):
    lex.update({"AI": "إيه آي"})
    assert lex.apply("مدير AI") == "مدير إيه آي"


def test_update_chains_and_reaches_the_normaliser():
    lex = Lexicon.builtin().update({"NDA": "اتفاقية عدم إفصاح"})
    assert "اتفاقية عدم إفصاح" in normalise("وقعنا NDA", lexicon=lex).tts


def test_load_from_disk_carries_its_own_licence(tmp_path):
    p = tmp_path / "mine.json"
    p.write_text(json.dumps({
        "meta": {"licence": "CC-BY-4.0"},
        "acronyms": {"ADNOC": "أدنوك"},
    }, ensure_ascii=False), encoding="utf-8")
    lex = Lexicon.load(p)
    assert lex.licence == "CC-BY-4.0"
    assert lex.apply("شركة ADNOC") == "شركة أدنوك"


def test_unknown_licence_is_reported_not_assumed():
    assert Lexicon.from_dict({"acronyms": {"X": "س"}}).licence == "unknown"


def test_a_bare_arabic_letter_is_never_rewritten(lex):
    # ص and م are ordinary letters far more often than they are clock periods.
    # Deciding AM/PM belongs to the time rule, where there is a clock to key off.
    assert lex.apply("ص م") == "ص م"

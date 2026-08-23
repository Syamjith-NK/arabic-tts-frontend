"""Rule-by-rule normalisation.

The minimum regression suite from the design brief is here verbatim, plus every
bug the benchmark run actually exposed. A case that came out of measured audio is
marked as such - those are the ones that must never regress silently.
"""
import pytest

from arabic_tts_frontend import Lexicon, normalise


def tts(text, **kw):
    return normalise(text, **kw).tts


# --------------------------------------------------------------------------- #
# the brief's minimum suite
# --------------------------------------------------------------------------- #

def test_arabic_indic_cardinal():
    assert tts("لدي ١٢٣ مستخدمًا") == "لدي مئة وثلاثة وعشرون مستخدمًا"


def test_currency_with_fils():
    assert tts("السعر 1,250.50 درهم") == "السعر ألف ومئتان وخمسون درهم وخمسون فلس"


def test_currency_code_before_amount():
    assert tts("التكلفة AED 1,250.50") == "التكلفة ألف ومئتان وخمسون درهم وخمسون فلس"


def test_percent():
    assert tts("النمو 25%") == "النمو خمسة وعشرون بالمئة"


def test_time_half_past():
    assert tts("موعدنا 08:30") == "موعدنا الثامنة والنصف"


def test_date():
    assert tts("تاريخ الإطلاق 20/08/2026") == "تاريخ الإطلاق عشرون أغسطس عام ألفان وستة وعشرون"


def test_phone_is_read_digit_by_digit():
    assert tts("اتصل على 0501234567") == (
        "اتصل على صفر خمسة صفر واحد اثنان ثلاثة أربعة خمسة ستة سبعة")


def test_version_is_not_a_decimal():
    assert tts("الإصدار 2.1.0") == "الإصدار اثنان نقطة واحد نقطة صفر"


# --------------------------------------------------------------------------- #
# bugs the measured run exposed - see README "What the numbers do not cover"
# --------------------------------------------------------------------------- #

def test_quarter_to_names_the_next_hour():
    """MEASURED FAILURE. 2:45 is الثالثة إلا الربع - quarter to THREE.
    Saying الثانية إلا الربع announces 1:45, an hour early."""
    assert "الثالثة إلا الربع" in tts("الاجتماع في الساعة 2:45 بعد الظهر.")


def test_never_contradicts_a_period_the_author_already_wrote():
    """MEASURED FAILURE. The sentence says بعد الظهر; appending صباحًا produced a
    self-contradicting utterance."""
    out = tts("الاجتماع في الساعة 2:45 بعد الظهر.")
    assert "صباح" not in out


def test_never_invents_a_period_for_an_ambiguous_hour():
    out = tts("موعدنا 2:45")
    assert "صباح" not in out and "مساء" not in out


def test_states_the_period_only_when_the_source_is_unambiguous():
    assert tts("في 14:00 غدا") == "في الثانية مساءً غدا"


def test_short_code_in_phone_context_is_not_a_quantity():
    """MEASURED FAILURE. `800 555` came out as ثمانمئة خمسمئة وخمسة وخمسون."""
    out = tts("للاستفسار يرجى الاتصال على الرقم 800 555.")
    assert out == "للاستفسار يرجى الاتصال على الرقم ثمانية صفر صفر خمسة خمسة خمسة."


@pytest.mark.parametrize("text,expected_fragment", [
    # A law number and a room number really are quantities. The five-digit floor
    # on the phone-context rule is what keeps them that way.
    ("القانون الاتحادي رقم 33 لسنة 2021", "رقم ثلاثة وثلاثون"),
    ("غرفة رقم 305", "رقم ثلاثمئة وخمسة"),
])
def test_phone_context_does_not_swallow_short_identifiers(text, expected_fragment):
    assert expected_fragment in tts(text)


def test_decimal_percent_is_one_number():
    """A percent pattern that matched only the digits after the point split
    2.5% into two unrelated numbers."""
    assert tts("ارتفع 2.5% هذا العام") == "ارتفع اثنان فاصلة خمسة بالمئة هذا العام"


def test_no_space_before_punctuation():
    """The lexicon pads its replacements; a stray space before a full stop is
    audible as a pause in some engines."""
    assert tts("النسبة ٤٧%.").endswith("بالمئة.")


# --------------------------------------------------------------------------- #
# ordering: the whole design is which rule gets to see the token first
# --------------------------------------------------------------------------- #

def test_date_wins_over_time_and_cardinal():
    assert normalise("20/08/2026").applied == ["date"]


def test_currency_wins_over_cardinal():
    assert "cardinal" not in normalise("500 AED").applied


def test_bare_decimal_stays_a_decimal():
    assert tts("النسبة 2.5") == "النسبة اثنان فاصلة خمسة"


def test_v_prefix_makes_a_pair_a_version():
    assert tts("v2.5 متاح") == "اثنان نقطة خمسة متاح"


# --------------------------------------------------------------------------- #
# both forms come back; the original is never destroyed
# --------------------------------------------------------------------------- #

def test_original_is_preserved_for_subtitles():
    n = normalise("في عام ٢٠٢٦")
    assert n.original == "في عام ٢٠٢٦"
    assert n.tts != n.original
    assert n.changed


def test_text_without_numbers_is_untouched():
    n = normalise("مرحبا بكم في الإمارات")
    assert n.tts == n.original
    assert not n.changed
    assert n.applied == []


def test_applied_reports_which_rules_fired():
    assert normalise("موعدنا ٠٨:٣٠").applied == ["fold_digits", "time"]


def test_lexicon_can_be_switched_off():
    empty = Lexicon(entries={})
    assert tts("مدير AI", lexicon=empty) == "مدير AI"
    assert "الذكاء" in tts("مدير AI")

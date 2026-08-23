"""Cardinal verbalisation. The cases here are the ones a naive implementation
gets wrong, not a sample of easy ones."""
import pytest

from arabic_tts_frontend.numbers import digit_by_digit, fold_digits, verbalise


@pytest.mark.parametrize("n,expected", [
    (0, "صفر"),
    (7, "سبعة"),
    (10, "عشرة"),
    (11, "أحد عشر"),
    (12, "اثنا عشر"),
    # The unit comes FIRST in Arabic: "one and twenty", not "twenty one".
    (21, "واحد وعشرون"),
    (47, "سبعة وأربعون"),
    (100, "مئة"),
    (101, "مئة وواحد"),
    (200, "مئتان"),
    (674, "ستمئة وأربعة وسبعون"),
    (1000, "ألف"),
    (1500, "ألف وخمسمئة"),
    (2000, "ألفان"),
    (2026, "ألفان وستة وعشرون"),
    (5000, "خمسة آلاف"),
    # A dual in idafa drops its nun: مئتا ألف, not مئتان ألف.
    (200_000, "مئتا ألف"),
    (1_200_000, "مليون ومئتا ألف"),
    (2_000_000, "مليونان"),
])
def test_cardinals(n, expected):
    assert verbalise(n) == expected


@pytest.mark.parametrize("n,expected", [
    (3, "ثلاث"),
    (11, "إحدى عشرة"),
    # The teens invert: masculine noun -> ثلاثة عشر, feminine -> ثلاث عشرة.
    (13, "ثلاث عشرة"),
    (21, "واحدة وعشرون"),
])
def test_feminine_agreement(n, expected):
    assert verbalise(n, feminine=True) == expected


def test_feminine_does_not_leak_into_scale_words():
    # The noun counted by ألف is ألف itself, which is masculine, whatever the
    # noun at the end of the phrase happens to be.
    assert verbalise(3000, feminine=True) == "ثلاثة آلاف"


def test_negative():
    assert verbalise(-5) == "سالب خمسة"


def test_fold_digits():
    assert fold_digits("٢٠٢٦") == "2026"
    assert fold_digits("۲۰۲۶") == "2026"
    # The Arabic decimal and thousands separators fold too, or the folded digits
    # sit around a token no later rule can match.
    assert fold_digits("١٢٣٤٫٥") == "1234.5"
    assert fold_digits("١٬٠٠٠") == "1,000"
    assert fold_digits("no digits") == "no digits"


def test_digit_by_digit_is_not_a_cardinal():
    assert digit_by_digit("0501") == "صفر خمسة صفر واحد"
    assert digit_by_digit("05-01") == "صفر خمسة صفر واحد"


def test_dual_nun_switch_reverts_to_the_form_that_survived_tts():
    """The construct-state dual is correct Arabic that Fish mishears as مائة.

    Measured in the 2026-08-24 A/B: مئتا ألف came back from ASR as مائة ألف, so
    the listener lost 1.1 million dirhams. The switch exists for that case.
    """
    from arabic_tts_frontend import numbers

    assert numbers.verbalise(1_200_000) == "مليون ومئتا ألف"
    numbers.DROP_DUAL_NUN = False
    try:
        assert numbers.verbalise(1_200_000) == "مليون ومئتان ألف"
    finally:
        numbers.DROP_DUAL_NUN = True
    assert numbers.verbalise(1_200_000) == "مليون ومئتا ألف"

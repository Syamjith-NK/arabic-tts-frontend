"""The scorer. This is how the README's numbers were produced, so a bug here is a
bug in the published measurement - which is exactly what happened once already
(see "Two bugs found in our own scorer" in the README)."""
import pytest

from arabic_tts_frontend import recovered, recovered_multi, words_to_values


@pytest.mark.parametrize("text,expected", [
    ("674", {674}),
    ("٦٧٤", {674}),
    ("ستمائة وأربعة وسبعون", {674}),
    ("مئة وثلاثة وعشرون", {123}),
    ("ألفين وستة وعشرين", {2026}),
    # "ستة مئة" is 600, not 6 + 100. Only a bare unit BEFORE a plain hundred multiplies.
    ("ستة مئة", {600}),
    ("مئة وستة", {106}),
])
def test_words_and_digits_reach_the_same_value(text, expected):
    assert words_to_values(text) == expected


def test_percent_marker_carries_no_value_of_its_own():
    # "سبعة وأربعون بالمئة" is 47%, not 147 - the prefix stripper used to turn
    # بالمئة into مئة and add it.
    assert words_to_values("سبعة وأربعون بالمئة") == {47}


def test_a_clock_reading_is_parts_not_a_sum():
    assert {12, 45} <= words_to_values("الساعة الثانية عشرة وخمسة وأربعين")


def test_a_date_ordinal_still_accumulates():
    # No ساعة in the sentence, so the clock gate stays shut and the twenty-eighth
    # is 28 rather than 8 and 20 separately.
    assert 28 in words_to_values("الثامن والعشرين من أغسطس")


def test_half_and_quarter_only_mean_minutes_under_a_clock():
    assert words_to_values("نصف الميزانية") == set()
    assert 30 in words_to_values("الساعة الثامنة والنصف")


def test_tanween_does_not_break_a_ten():
    # The diacritic strips out but the alef it sat on does not, so "سبعونًا"
    # survived as "سبعونا", missed the tens table, and 674 read as 604.
    assert words_to_values("ستمائة وأربعة وسبعونًا") == {674}


def test_al_stripping_never_destroys_thousand():
    assert 1000 in words_to_values("ألف")


def test_recovered_accepts_a_year_read_as_two_pairs():
    # A year is often read as two pairs. A listener hears it correctly either way.
    assert recovered("2026", "قيلت ٢٠ ٢٦")


def test_recovered_multi_accepts_a_summed_clock():
    # 6:30 spoken as السادسة وثلاثين accumulates to 36. A listener hears it right
    # either way, so the scorer accepts it rather than punishing correct speech.
    assert recovered_multi("6:30", "السادسة وثلاثين")


def test_a_genuine_miss_is_still_a_miss():
    assert not recovered("674", "ستمائة وأربعة")


def test_no_expected_number_is_vacuously_recovered():
    assert recovered("لا أرقام", "أي شيء")


def test_quarter_to_is_a_subtraction():
    # الثالثة إلا الربع is 2:45. Read as an addition it puts the meeting half an
    # hour late; read as 3 + 15 it marks a correctly-speaking engine wrong.
    assert {2, 45} <= words_to_values("الاجتماع الساعة الثالثة إلا الربع")


def test_quarter_to_wraps_at_one_oclock():
    assert {12, 45} <= words_to_values("الساعة الواحدة إلا الربع")


def test_illa_outside_a_clock_is_left_alone():
    # Outside a clock الربع is "a quarter" - of a year, of a budget - and carries
    # no numeric value at all. Mapping it to 15 unconditionally would be a new bug.
    assert words_to_values("لا شيء إلا الربع الأخير من العام") == set()


def test_the_package_can_read_back_what_it_writes():
    # An idafa dual (مئتا ألف) is what our own verbaliser emits for 200,000. A
    # parser that cannot read it turns every round-trip check into a false alarm.
    from arabic_tts_frontend import verbalise
    for n in (200_000, 1_200_000, 2026, 674, 1500):
        assert n in words_to_values(verbalise(n))

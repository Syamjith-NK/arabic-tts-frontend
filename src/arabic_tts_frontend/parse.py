"""Read every number out of Arabic text as a VALUE - digits or words alike.

This is the scoring half of the package: it is how the numbers in the README were
measured, and it is shipped so anyone can re-run that measurement rather than take
it on trust. `normalize` writes numbers as words; `parse` reads them back.

Whisper writes numbers back either as digits ("674") or as Arabic words
("ستمائة وأربعة وسبعون"), and which one it picks is arbitrary. A scorer that only
looks for digits therefore marks correct speech as a failure - that bug understated
the first run of this benchmark and is exactly the kind of thing that makes a
published eval worthless.

So: parse Arabic number words into values, and compare on VALUES.

Clock time is handled under an explicit gate. `نصف` is "half" and `ربع` is "quarter"
in any context - a half of a budget, a quarter of a year - so they are only read as
30 and 15 when the sentence actually contains `ساعة` (hour). The same gate closes the
number group after an hour ordinal, so "الساعة الثانية عشرة وخمسة وأربعين" yields
{12, 45} rather than a summed 57. Outside that gate a date ordinal still accumulates
normally, which is what keeps "الثامن والعشرين" (the twenty-eighth) equal to 28.
"""
from __future__ import annotations

import re

A2W = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

UNITS = {
    "صفر": 0, "واحد": 1, "احد": 1, "أحد": 1, "اثنان": 2, "اثنين": 2, "إثنين": 2,
    "ثلاثة": 3, "ثلاث": 3, "الثالث": 3, "اربعة": 4, "أربعة": 4, "اربع": 4, "أربع": 4,
    "خمسة": 5, "خمس": 5, "ستة": 6, "ست": 6, "سبعة": 7, "سبع": 7,
    "ثمانية": 8, "ثمان": 8, "ثماني": 8, "تسعة": 9, "تسع": 9, "عشرة": 10, "عشر": 10,
    "احدى": 1, "إحدى": 1,
}
TEENS = {
    "احدعشر": 11, "اثنا": 2, "اثني": 2, "اثناعشر": 12, "ثلاثةعشر": 13, "اربعةعشر": 14, "خمسةعشر": 15,
    "ستةعشر": 16, "سبعةعشر": 17, "ثمانيةعشر": 18, "تسعةعشر": 19,
}
TENS = {
    "عشرون": 20, "عشرين": 20, "ثلاثون": 30, "ثلاثين": 30, "اربعون": 40, "أربعون": 40,
    "اربعين": 40, "أربعين": 40, "خمسون": 50, "خمسين": 50, "ستون": 60, "ستين": 60,
    "سبعون": 70, "سبعين": 70, "ثمانون": 80, "ثمانين": 80, "تسعون": 90, "تسعين": 90,
}
HUNDREDS = {
    "مئة": 100, "مائة": 100, "مية": 100, "مئتان": 200, "مئتين": 200, "مائتين": 200,
    "ثلاثمائة": 300, "ثلاثمئة": 300, "اربعمائة": 400, "أربعمائة": 400, "اربعمئة": 400,
    "خمسمائة": 500, "خمسمئة": 500, "ستمائة": 600, "ستمئة": 600,
    "سبعمائة": 700, "سبعمئة": 700, "ثمانمائة": 800, "ثمانمئة": 800,
    "تسعمائة": 900, "تسعمئة": 900, "مئتي": 200, "مائتي": 200,
    "مئاتين": 200, "مائتان": 200,      # spelling variants seen in real transcripts
    # A dual in idafa drops its nun - مئتا ألف. Our own verbaliser emits this, so
    # without it the package could not read back a number it had just written.
    "مئتا": 200, "مائتا": 200, 
}
# Ordinals. Arabic says times and dates ordinally - "الساعة السادسة" (the sixth hour)
# and "الثامن والعشرين" (the twenty-eighth). Without these the scorer punishes an
# engine for speaking correctly, which silently favoured whichever engine happened to
# read digits out flatly.
ORDINALS = {
    "الاول": 1, "الأول": 1, "الاولى": 1, "الأولى": 1,
    "الثاني": 2, "الثانية": 2, "الثالث": 3, "الثالثة": 3,
    "الرابع": 4, "الرابعة": 4, "الخامس": 5, "الخامسة": 5,
    "السادس": 6, "السادسة": 6, "السابع": 7, "السابعة": 7,
    "الثامن": 8, "الثامنة": 8, "التاسع": 9, "التاسعة": 9,
    "العاشر": 10, "العاشرة": 10, "الحادية": 11,
    # One o'clock is الواحدة, not الأولى - it is the form our own normaliser emits
    # and the one every clock in Arabic actually says.
    "الواحدة": 1,
    # Pre-joined, because these ordinals are written as TWO words ("الثانية عشرة").
    # `_join_ordinals` glues the pair back together before lookup; without it
    # "الحادية عشرة" (eleventh) read as 11 + 10 = 21.
    "الثانيةعشرة": 12, "الثانيةعشر": 12, "الحاديةعشرة": 11, "الحاديةعشر": 11,
}
# Fractions of an hour. GATED on a time context - see the module docstring. Mapping
# نصف to 30 unconditionally would be a new bug, not a fix.
FRACTIONS = {"نصف": 30, "ربع": 15, "ثلث": 20}
# "إلا" makes the fraction a SUBTRACTION from the coming hour: "الثالثة إلا الربع"
# is 2:45, not 3:15. Reading it as an addition puts the meeting 30 minutes late,
# and reading it as 3 + 15 marks a correctly-speaking engine wrong.
_EXCEPT = {"الا", "إلا"}
SCALES = {"الف": 1000, "ألف": 1000, "الفا": 1000, "ألفا": 1000, "الفان": 2000,
          "ألفان": 2000, "الفين": 2000, "ألفين": 2000, "آلاف": 1000,
          "مليون": 1_000_000, "مليونان": 2_000_000, "مليونين": 2_000_000, "ملايين": 1_000_000}

_STRIP = re.compile(r"^(ال|و|بال|لل)+")

# "بالمئة" / "في المئة" mean PER CENT, not one hundred. The prefix stripper made
# them "مئة" = 100 and ADDED it, so a correctly spoken "سبعة وأربعون بالمئة" (47%)
# parsed as 147 and scored LOST. A percent marker carries no value of its own.
_PERCENT_WORDS = {"بالمئة", "بالمائة", "المئة", "المائة", "بالمأة", "بالمئه", "بالمة"}

# "ثلاثة نقطة خمسة" is 3.5 read aloud. Without this, a decimal an engine said
# correctly came back as two unrelated integers.
_DECIMAL_WORDS = {"نقطة", "فاصلة", "فاصله", "نقطه"}


ALL_DICTS = (TEENS, HUNDREDS, TENS, SCALES, ORDINALS, FRACTIONS, UNITS)


def _clean(tok: str) -> str:
    tok = re.sub(r"[^ء-ي0-9]", "", tok.translate(A2W))
    return tok


def _detanween(tok: str) -> str:
    """Drop the alef that tanween leaves behind.

    `_clean` removes the diacritic itself (U+064B is outside ء-ي) but not the
    alef it sits on, so "سبعونًا" survives as "سبعونا", misses TENS, and 674 reads
    as 604. Guarded on length so a two-letter word is never reduced to one.
    """
    return tok[:-1] if len(tok) > 2 and tok.endswith("ا") else tok


def _known(tok: str) -> bool:
    return bool(tok) and any(tok in d for d in ALL_DICTS)


def _norm(raw: str) -> str:
    """The dictionary key a token should be looked up under.

    Order matters. A word already in a dictionary always wins over the prefix
    stripper - blind "ال" stripping destroys "الف" (thousand) by turning it into "ف".
    Only once both the written and the de-tanweened form have missed do we strip.
    """
    for cand in (raw, _detanween(raw)):
        if _known(cand):
            return cand
    stripped = _STRIP.sub("", raw)
    for cand in (stripped, _detanween(stripped)):
        if _known(cand):
            return cand
    return stripped or raw


def _join_ordinals(toks: list[str]) -> list[str]:
    """"الثانية عشرة" is ONE ordinal (twelfth) written as two words.

    A dictionary can only hold it pre-joined, so the pair is glued back together
    here, before lookup. Only a pair that actually resolves to an ordinal is joined,
    so "الثالث عشرة" is left alone rather than silently invented.
    """
    out: list[str] = []
    i = 0
    while i < len(toks):
        a = _norm(toks[i])
        if i + 1 < len(toks) and a in ORDINALS:
            b = _norm(toks[i + 1])
            if b in ("عشرة", "عشر") and (a + b) in ORDINALS:
                out.append(a + b)
                i += 2
                continue
        out.append(toks[i])
        i += 1
    return out


def _resolve_quarter_to(toks: list[str], out: set, clock: bool) -> tuple[list[str], set]:
    """Pull "<hour> إلا <fraction>" out of the token stream as an explicit time.

    It is removed rather than left for the main loop because the loop accumulates,
    and there is no addition that turns الثالثة إلا الربع into 2:45.
    """
    if not clock:
        return toks, out
    keep, i = [], 0
    while i < len(toks):
        a = _norm(toks[i])
        if (a in ORDINALS and i + 2 < len(toks)
                and _clean(toks[i + 1]) in _EXCEPT
                and _norm(toks[i + 2]) in FRACTIONS):
            hour = ORDINALS[a] - 1 or 12
            out.add(hour)
            out.add(60 - FRACTIONS[_norm(toks[i + 2])])
            i += 3
            continue
        keep.append(toks[i])
        i += 1
    return keep, out


def words_to_values(text: str) -> set[int]:
    """Every number expressed in `text`, as values - digits and words alike."""
    out: set[int] = set()
    text = text.translate(A2W)
    for d in re.findall(r"\d+(?:[.:,]\d+)*", text):
        parts = re.split(r"[.:,]", d)
        if len(parts) > 1:
            for pnum in parts:          # 6:30 / 6.30 -> both 6 and 30 are heard
                if pnum:
                    out.add(int(pnum))
        try:
            out.add(int(float(d.replace(",", ".").split(":")[0])))
        except ValueError:
            pass

    # A clock reading behaves differently from every other number: its parts are
    # separate values, not addends. Gate that on the sentence actually saying "hour".
    clock = "ساعة" in text
    # Spoken decimals: "<a> نقطة <b>" -> a.b, added as a string-comparable value.
    _rt = text.split()
    for _i, _t in enumerate(_rt):
        if _clean(_t) in _DECIMAL_WORDS and 0 < _i < len(_rt) - 1:
            for _a in words_to_values(_rt[_i - 1]):
                for _b in words_to_values(_rt[_i + 1]):
                    out.add(f"{_a}.{_b}")  # type: ignore[arg-type]

    toks = _join_ordinals([_clean(t) for t in text.split()])
    toks, out = _resolve_quarter_to(toks, out, clock)
    cur = 0            # value being accumulated in the current group
    total = 0          # groups already closed by a scale word
    seen = False
    for raw in toks:
        if _clean(raw) in _PERCENT_WORDS:
            if seen and (cur or total):
                out.add(total + cur)
            cur = total = 0; seen = False
            continue
        t = _norm(raw)
        if t in TEENS:
            cur += TEENS[t]; seen = True
        elif t in HUNDREDS:
            h = HUNDREDS[t]
            # "ستة مئة" = 600, not 6 + 100. Only a bare 1-9 immediately before a
            # plain hundred multiplies it; "مئة وستة" (106) is unaffected because
            # the unit comes AFTER.
            if h == 100 and 1 <= cur <= 9:
                cur *= 100
            else:
                cur += h
            seen = True
        elif t in TENS:
            cur += TENS[t]; seen = True
        elif t in SCALES:
            mult = SCALES[t]
            if mult >= 1000 and mult in (2000,):        # "ألفان" is itself 2000
                total += mult
            else:
                total += (cur or 1) * mult
            cur = 0; seen = True
        elif t in ORDINALS:
            cur += ORDINALS[t]; seen = True
            if clock:
                # The hour closes the group. Otherwise "الثانية عشرة وخمسة
                # وأربعين" accumulates 12+5+40 into a single 57 and both the hour
                # and the minutes are lost. Dates are untouched - they have no "ساعة".
                out.add(total + cur)
                cur = total = 0; seen = False
        elif clock and t in FRACTIONS:
            cur += FRACTIONS[t]; seen = True
        elif t in UNITS:
            cur += UNITS[t]; seen = True
        else:
            if seen and (cur or total):
                out.add(total + cur)
                cur = total = 0; seen = False
    if seen and (cur or total):
        out.add(total + cur)
    return {v for v in out if v}


def recovered(expect: str, heard: str) -> bool:
    """Did every number in `expect` survive into `heard`, in any written form?"""
    want = words_to_values(expect)
    got = words_to_values(heard)
    if not want:
        return True
    # a year like 2026 may be spoken as "twenty twenty-six" -> {20, 26}; accept the
    # split reading too, since a listener hears it correctly either way
    for w in want:
        if w in got:
            continue
        s = str(w)
        if len(s) == 4 and {int(s[:2]), int(s[2:])} <= got:
            continue
        return False
    return True


def recovered_multi(expect: str, heard: str) -> bool:
    """As `recovered`, but a compound like a time may also arrive summed.

    "6:30" spoken as "السادسة وثلاثين" accumulates to 36 rather than {6, 30}. A
    listener hears it correctly either way, so accept the sum too.
    """
    if recovered(expect, heard):
        return True
    parts = [int(x) for x in re.findall(r"\d+", expect.translate(A2W))]
    if len(parts) > 1 and sum(parts) in words_to_values(heard):
        return True
    return False

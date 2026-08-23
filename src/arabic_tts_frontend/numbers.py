"""Arabic cardinal number verbalisation.

The inverse of the ArNum-TTS parser: turn 2026 into ألفان وستة وعشرون so a TTS
engine can say it, because measurement showed engines either mangle digits or
skip them entirely.

Arabic number order is not English order. 21 is "one and twenty"
(واحد وعشرون) - the unit comes FIRST and is joined with و. Getting that
backwards is the single most common mistake in naive implementations.
"""
from __future__ import annotations

ARABIC_INDIC = "٠١٢٣٤٥٦٧٨٩"
EASTERN = "۰۱۲۳۴۵۶۷۸۹"
_FOLD = {ord(c): str(i) for i, c in enumerate(ARABIC_INDIC)}
_FOLD.update({ord(c): str(i) for i, c in enumerate(EASTERN)})
# Arabic uses U+066B/U+066C as decimal and thousands separators. Folding the
# digits but leaving these turns ١٢٣٤٫٥ into a token no rule matches.
_FOLD[0x066B] = "."
_FOLD[0x066C] = ","


def fold_digits(text: str) -> str:
    """Arabic-Indic and Eastern Arabic digits -> Western. Folding alone is NOT a
    fix: an engine that cannot say 2026 still cannot say it. Verbalise after."""
    return text.translate(_FOLD)


# Arabic numbers agree in gender with the counted noun, which is why every entry
# point takes a `feminine` flag - see the limits section of the README.
UNITS_M = ["صفر", "واحد", "اثنان", "ثلاثة", "أربعة", "خمسة", "ستة", "سبعة", "ثمانية", "تسعة"]
UNITS_F = ["صفر", "واحدة", "اثنتان", "ثلاث", "أربع", "خمس", "ست", "سبع", "ثمان", "تسع"]
TEENS_M = ["عشرة", "أحد عشر", "اثنا عشر", "ثلاثة عشر", "أربعة عشر", "خمسة عشر",
           "ستة عشر", "سبعة عشر", "ثمانية عشر", "تسعة عشر"]
# The teens invert: the *masculine* counted noun takes ثلاثة عشر, the feminine
# takes ثلاث عشرة. The unit and the ten disagree with each other on purpose.
TEENS_F = ["عشر", "إحدى عشرة", "اثنتا عشرة", "ثلاث عشرة", "أربع عشرة", "خمس عشرة",
           "ست عشرة", "سبع عشرة", "ثماني عشرة", "تسع عشرة"]
TENS = ["", "", "عشرون", "ثلاثون", "أربعون", "خمسون", "ستون", "سبعون", "ثمانون", "تسعون"]
HUNDREDS = ["", "مئة", "مئتان", "ثلاثمئة", "أربعمئة", "خمسمئة",
            "ستمئة", "سبعمئة", "ثمانمئة", "تسعمئة"]


def _under_hundred(n: int, feminine: bool) -> str:
    units = UNITS_F if feminine else UNITS_M
    if n < 10:
        return units[n]
    if n < 20:
        return (TEENS_F if feminine else TEENS_M)[n - 10]
    tens, unit = divmod(n, 10)
    if unit == 0:
        return TENS[tens]
    # unit FIRST, then the ten: واحد وعشرون
    return f"{units[unit]} و{TENS[tens]}"


def _under_thousand(n: int, feminine: bool) -> str:
    h, rest = divmod(n, 100)
    parts = []
    if h:
        parts.append(HUNDREDS[h])
    if rest:
        parts.append(_under_hundred(rest, feminine))
    return " و".join(parts)


# (upper bound, dual form, plural 3-10, singular)
_SCALES = (
    (10**6, "ألفان", "آلاف", "ألف"),
    (10**9, "مليونان", "ملايين", "مليون"),
    (10**12, "ملياران", "مليارات", "مليار"),
)


# A dual noun in idafa (annexed to what follows) loses its final nun: مئتان
# standing alone, but مئتا ألف - "two hundred thousand". Leaving the nun on is
# audibly wrong to any Arabic speaker, and 200,000 is a common enough figure that
# it shows up in the first page of any budget script.
_DUAL_IDAFA = {"مئتان": "مئتا", "ألفان": "ألفا", "مليونان": "مليونا", "ملياران": "مليارا"}

# MEASURED HAZARD (A/B re-run, 2026-08-24, Fish s2.1-pro-free + faster-whisper medium):
# the grammatically correct مئتا ألف is MISHEARD as مائة ألف - the listener gets
# 100,000 instead of 1,200,000 - while the technically-wrong مئتان ألف survives.
# Two of the 45 sentences flipped OK->MISS on exactly this word and nothing else.
# So "correct Arabic" and "Arabic this engine can say" are not the same target.
# n=2 on one engine is too thin to flip the default, hence a switch rather than a
# rewrite: set DROP_DUAL_NUN = False if you are voicing through an engine that
# swallows the construct-state dual. See arabic_numeral_bench/results_fish_shipped.jsonl.
DROP_DUAL_NUN = True


def _drop_dual_nun(words: str) -> str:
    if not DROP_DUAL_NUN:
        return words
    last = words.rsplit(" ", 1)[-1]
    return words[: len(words) - len(last)] + _DUAL_IDAFA.get(last, last)


def verbalise(n: int, feminine: bool = False) -> str:
    """A non-negative integer as Arabic words.

    `feminine` follows the gender of the counted noun and only reaches the last
    group - 21 سيارة is إحدى وعشرون سيارة, but the ألف in 21,000 stays masculine
    because the noun it counts is ألف itself.
    """
    if n < 0:
        return "سالب " + verbalise(-n, feminine)
    if n < 100:
        return _under_hundred(n, feminine)
    if n < 1000:
        return _under_thousand(n, feminine)

    for limit, two, plural, single in _SCALES:
        if n < limit:
            scale = limit // 1000
            count, rest = divmod(n, scale)
            if count == 1:
                head = single
            elif count == 2:
                head = two
            elif 3 <= count <= 10:
                head = f"{_under_hundred(count, False)} {plural}"
            else:
                # 11+ takes the SINGULAR after it: أحد عشر ألفًا, not آلاف.
                head = f"{_drop_dual_nun(_under_thousand(count, False))} {single}"
            return head if not rest else f"{head} و{verbalise(rest, feminine)}"
    return str(n)


def digit_by_digit(s: str, sep: str = " ") -> str:
    """Read a string one digit at a time - phone numbers, IDs, codes.

    A phone number read as a cardinal ("five hundred one thousand two hundred...")
    is worse than not converting it at all, which is why this is a separate entry
    point and never a fallback of `verbalise`.
    """
    return sep.join(UNITS_M[int(c)] for c in s if c.isdigit())

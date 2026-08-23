"""Context-aware Arabic text normalisation for speech synthesis.

One generic number converter is the mistake. A phone number read as a cardinal
("five hundred one thousand two hundred...") is worse than not converting it at
all, and a year read as a quantity sounds wrong to any Arabic speaker.

So: classify first, convert per class, and leave the original text alone for
subtitles. Callers get BOTH forms back.

The pass order is the design, not an accident:

    fold digits  ->  STRUCTURAL rules  ->  lexicon  ->  GENERIC number rules

Structural rules run first because they need the raw token: `AED 1,250.50` is a
currency only while `AED` is still `AED`, and `0501234567` is a phone number only
before something reads it as a quantity. The lexicon runs next so `km²` and `CEO`
become Arabic words. Generic number rules run last, over whatever is left, which
is by then guaranteed to be a plain quantity.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

from .lexicon import Lexicon
from .numbers import digit_by_digit, fold_digits, verbalise

MONTHS = {
    1: "يناير", 2: "فبراير", 3: "مارس", 4: "أبريل", 5: "مايو", 6: "يونيو",
    7: "يوليو", 8: "أغسطس", 9: "سبتمبر", 10: "أكتوبر", 11: "نوفمبر", 12: "ديسمبر",
}
# Clock hours are ORDINAL and feminine in Arabic: "the second hour", not "two".
HOUR_ORD = ["", "الواحدة", "الثانية", "الثالثة", "الرابعة", "الخامسة", "السادسة",
            "السابعة", "الثامنة", "التاسعة", "العاشرة", "الحادية عشرة", "الثانية عشرة"]
# Currency code / symbol -> (major unit, minor unit or None).
CURRENCIES = {
    "AED": ("درهم", "فلس"), "درهم": ("درهم", "فلس"), "د.إ": ("درهم", "فلس"),
    "SAR": ("ريال", "هللة"), "ر.س": ("ريال", "هللة"),
    "USD": ("دولار", "سنت"), "$": ("دولار", "سنت"),
    "EUR": ("يورو", "سنت"), "€": ("يورو", "سنت"),
    "GBP": ("جنيه إسترليني", "بنس"), "£": ("جنيه إسترليني", "بنس"),
    "KWD": ("دينار", "فلس"), "BHD": ("دينار", "فلس"), "OMR": ("ريال", "بيسة"),
    "QAR": ("ريال", "درهم"), "EGP": ("جنيه", "قرش"),
}
_CUR_ALT = "|".join(sorted((re.escape(k) for k in CURRENCIES), key=len, reverse=True))

# Words that mean a digit string is an identifier, not a quantity. Without this a
# six-digit short code like "800 555" is read as eight hundred / five hundred and
# fifty-five, which is what the benchmark measured it doing.
#
# The five-digit floor is what keeps `القانون رقم 33` and `غرفة رقم 305` as
# quantities: those really are numbers, and spelling a law out digit by digit is
# the same class of error in the other direction.
_PHONE_CTX = (r"(?:الرقم|رقم|الهاتف|هاتف|الجوال|جوال|موبايل|الفاكس|فاكس|تحويلة"
              r"|اتصل\s+على|الاتصال\s+على|الرمز|رمز)")
# A period the author already stated. Never append a second one.
_PERIOD_WORDS = ("صباح", "مساء", "ظهر", "ليل", "فجر", "عصر", "AM", "PM", "am", "pm")


@dataclass
class Normalised:
    original: str                       # unchanged - use for subtitles and the UI
    tts: str                            # verbalised - send this to the engine
    applied: list[str] = field(default_factory=list)   # which rules fired, in order

    @property
    def changed(self) -> bool:
        return self.tts != self.original


# --------------------------------------------------------------------------- #
# structural rules - they need the raw token, so they run before anything else
# --------------------------------------------------------------------------- #

def _phone_in_context(m: re.Match, ctx: str) -> str:
    return m.group("ctx") + digit_by_digit(m.group("num"))


def _phone(m: re.Match, ctx: str) -> str:
    # Digit by digit. Never a cardinal.
    return digit_by_digit(m.group(0))


def _version(m: re.Match, ctx: str) -> str:
    """`2.1.0` is three numbers, not two and a half.

    Only fires on three-or-more components, or on a `v`-prefixed pair. A bare
    `2.5` stays a decimal, because that is what it usually is.
    """
    parts = [p for p in re.split(r"\.", m.group("num")) if p != ""]
    return " نقطة ".join(verbalise(int(p)) for p in parts)


def _date(m: re.Match, ctx: str) -> str:
    d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if not (1 <= mo <= 12 and 1 <= d <= 31):
        return m.group(0)
    return f"{verbalise(d)} {MONTHS[mo]} عام {verbalise(y)}"


def _time(m: re.Match, ctx: str) -> str:
    """`H:MM` spoken as Arabic clock time.

    Two rules that are easy to get wrong and both reach the listener as FACT:

    1. "إلا الربع" is quarter TO the NEXT hour. 2:45 is `الثالثة إلا الربع`, not
       `الثانية إلا الربع` - the latter says 1:45. An hour-early time is worse
       than any mispronunciation.
    2. **Never invent AM/PM.** A bare `2:45` does not say which. Appending صباحًا
       fabricated a fact and, when the sentence already said بعد الظهر, produced a
       self-contradicting utterance. The period is stated only when the source is
       unambiguous (a 24-hour hour) AND the sentence has not already said it.
    """
    h, mi = int(m.group(1)), int(m.group(2))
    if h > 23 or mi > 59:
        return m.group(0)
    already_stated = any(w in ctx for w in _PERIOD_WORDS)
    suffix = ""
    if (h >= 13 or h == 0) and not already_stated:
        suffix = " صباحًا" if h < 12 else " مساءً"

    h12 = h % 12 or 12
    if mi == 45:
        nxt = (h12 % 12) + 1          # quarter TO the next hour
        return HOUR_ORD[nxt] + " إلا الربع" + suffix
    out = HOUR_ORD[h12]
    if mi == 0:
        pass
    elif mi == 30:
        out += " والنصف"
    elif mi == 15:
        out += " والربع"
    else:
        out += f" و{verbalise(mi, feminine=True)} دقيقة"
    return out + suffix


def _currency(m: re.Match, ctx: str) -> str:
    major, minor = CURRENCIES[m.group("cur")]
    whole = int(m.group("whole").replace(",", ""))
    frac = m.group("frac")
    out = f"{verbalise(whole)} {major}"
    if frac and int(frac):
        # ".5" on a two-decimal currency is fifty, not five.
        sub = int(frac.ljust(2, "0")) if len(frac) < 2 else int(frac)
        out += f" و{verbalise(sub)} {minor}"
    return out


# --------------------------------------------------------------------------- #
# generic rules - everything left is a plain quantity by the time these run
# --------------------------------------------------------------------------- #

def _spoken_number(tok: str) -> str:
    """A bare numeric token - integer or decimal - as words."""
    if "." in tok:
        whole, frac = tok.split(".", 1)
        return f"{verbalise(int(whole))} فاصلة {verbalise(int(frac))}"
    return verbalise(int(tok.replace(",", "")))


def _percent(m: re.Match, ctx: str) -> str:
    # Must swallow the decimal part too. Matching only the digits after the point
    # turned 2.5% into "two point five" spelled as two separate numbers.
    return f"{_spoken_number(m.group(1))} بالمئة"


def _decimal(m: re.Match, ctx: str) -> str:
    return f"{verbalise(int(m.group(1)))} فاصلة {verbalise(int(m.group(2)))}"


def _cardinal(m: re.Match, ctx: str) -> str:
    return verbalise(int(m.group(0).replace(",", "")))


Rule = tuple[str, re.Pattern[str], Callable[[re.Match, str], str]]

#: Order is the design. Phone and ID patterns must win before anything can read
#: them as a quantity; date before time before plain numbers.
STRUCTURAL: list[Rule] = [
    ("phone_context", re.compile(
        rf"(?P<ctx>{_PHONE_CTX}\s*(?:هو\s*|:\s*)?)(?P<num>\+?\d[\d\s\-]{{3,20}}\d)"), _phone_in_context),
    ("phone_intl", re.compile(r"\+\d{1,4}[\s-]?\d{1,3}[\s-]?\d{3}[\s-]?\d{4}\b"), _phone),
    ("phone_local", re.compile(r"\b0\d{1,2}[\s-]?\d{3}[\s-]?\d{4}\b"), _phone),
    ("version", re.compile(r"\bv?(?P<num>\d+(?:\.\d+){2,})\b"), _version),
    ("version_v", re.compile(r"\bv(?P<num>\d+\.\d+)\b"), _version),
    ("date", re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b"), _date),
    ("time", re.compile(r"\b(\d{1,2}):(\d{2})\b"), _time),
    ("currency_pre", re.compile(
        rf"(?P<cur>{_CUR_ALT})\s*(?P<whole>\d[\d,]*)(?:\.(?P<frac>\d{{1,2}}))?"), _currency),
    ("currency_post", re.compile(
        rf"(?P<whole>\d[\d,]*)(?:\.(?P<frac>\d{{1,2}}))?\s*(?P<cur>{_CUR_ALT})"), _currency),
]

GENERIC: list[Rule] = [
    ("percent", re.compile(r"\b(\d+(?:\.\d+)?)\s*%"), _percent),
    ("decimal", re.compile(r"\b(\d+)\.(\d+)\b"), _decimal),
    ("cardinal", re.compile(r"\b\d[\d,]*\b"), _cardinal),
]


def _run(rules: list[Rule], text: str, applied: list[str]) -> str:
    for name, pattern, fn in rules:
        # `ctx` is the whole sentence as it stands: a rule that must not
        # contradict what the author already wrote needs to see it.
        new = pattern.sub(lambda m, f=fn: f(m, text), text)
        if new != text:
            applied.append(name)
            text = new
    return text


def normalise(text: str, lexicon: Lexicon | None = None) -> Normalised:
    """Return the original text and a TTS-safe verbalised form.

    `lexicon` defaults to the built-in MIT table. Pass `Lexicon.builtin().update(...)`
    to add your own terms, or `Lexicon(entries={})` to switch it off entirely.
    """
    lex = Lexicon.builtin() if lexicon is None else lexicon
    applied: list[str] = []

    work = fold_digits(text)
    if work != text:
        applied.append("fold_digits")
    work = _run(STRUCTURAL, work, applied)

    lexed = lex.apply(work)
    if lexed != work:
        applied.append("lexicon")
    work = lexed

    work = _run(GENERIC, work, applied)
    work = re.sub(r"\s{2,}", " ", work)
    # The lexicon pads its replacements, which leaves a gap before any trailing
    # punctuation. A stray space there is audible as a pause in some engines.
    work = re.sub(r"\s+([.,،؛؟!:])", r"\1", work).strip()
    return Normalised(original=text, tts=work, applied=applied)

"""The Arabic voice front-end: text in, speech-ready text out, with confidence.

    raw text
      -> 1. NORMALISE    numbers, dates, currency, times, phone numbers -> words
      -> 2. LEXICON      units, currency codes, acronyms, abbreviations
      -> 3. DIACRITISE   optional, lexicon-first, per-word confidence
      -> 4. speak        any TTS engine (Fish, ElevenLabs, Apple, ...)

Order matters and is not arbitrary: `2021` must become `ألفان وواحد وعشرون` BEFORE
diacritisation, or the diacritiser sees a digit string, calls it unknown, and hands
the engine a bare numeral - the exact failure that scored 0/15 on Arabic-Indic input.

Step 3 is off unless you pass a lexicon file, because no diacritisation lexicon ships
with this package: the only one measured was built from a GPL-2.0 corpus. Steps 1-2
are the measured win and need nothing external.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .diacritics import Diacritiser, Word
from .lexicon import Lexicon
from .normalize import normalise


@dataclass
class Prepared:
    original: str                       # untouched - use for subtitles and the UI
    spoken: str                         # send THIS to the engine
    uncertain: list[Word] = field(default_factory=list)
    coverage: float = 1.0
    applied: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return self.spoken != self.original

    def report(self) -> str:
        pct = round(100 * self.coverage)
        if not self.uncertain:
            return f"{pct}% certain - nothing to review"
        worst = ", ".join(f"{w.surface}({w.variants})" for w in self.uncertain[:8])
        return f"{pct}% certain - review: {worst}"


class VoiceFrontEnd:
    """Prepare Arabic text for any TTS engine.

    >>> fe = VoiceFrontEnd()
    >>> fe.prepare("في عام ٢٠٢٦ ارتفعت النسبة إلى ٤٧%.").spoken
    'في عام ألفان وستة وعشرون ارتفعت النسبة إلى سبعة وأربعون بالمئة.'
    """

    def __init__(self, diacritics_lexicon: str | Path | None = None,
                 lexicon: Lexicon | None = None) -> None:
        self.lexicon = lexicon or Lexicon.builtin()
        self.dia = Diacritiser(diacritics_lexicon) if diacritics_lexicon else None

    @property
    def diacritics_licence(self) -> str:
        """The diacritics lexicon's licence - NOT the engine's. Callers shipping
        commercially must check it: a GPL-2.0 lexicon cannot go inside a
        proprietary product."""
        return self.dia.licence if self.dia else "n/a - diacritisation disabled"

    def prepare(self, text: str) -> Prepared:
        n = normalise(text, lexicon=self.lexicon)
        if self.dia is None:
            return Prepared(original=text, spoken=n.tts, applied=n.applied)
        d = self.dia(n.tts)
        return Prepared(
            original=text,
            spoken=d.text,
            uncertain=d.uncertain,
            coverage=d.coverage,
            applied=n.applied + ["diacritise"],
        )

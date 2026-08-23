"""Lexicon-first Arabic diacritiser.

Chosen over a neural model on measured evidence, not taste: on the same 60 rows a
plain most-frequent-form lexicon beat a 300M seq2seq **2x on WER-no-case**
(11.0% vs 21.91%) — the metric that decides whether a word is *pronounced* right.
See the "Diacritisation" section of the README.

**No lexicon ships with this package.** The only one measured was built from
Tashkeela, which is GPL-2.0; bundling it would relicense the engine. Build your own
with a permissive or owned corpus - the loader does not care which file it gets, and
`Diacritiser.licence` reports whatever the file declares.

The thing no competitor ships: **per-word confidence.** Every word comes back
labelled, so a caller can act on doubt instead of discovering it in the audio:

  certain   - exactly one diacritisation ever attested for this skeleton
  ambiguous - several attested; we used the most frequent one
  unknown   - not in the lexicon; passed through bare

A TTS engine given a bare word guesses silently. We can hand the caller a list of
the words we were unsure about, which is what makes a review UI - or a targeted
model call on just those words - possible.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

DIAC = set(map(chr, range(0x064B, 0x0653))) | {"ٰ", "ٓ", "ٔ", "ٕ"}
_TOKEN = re.compile(r"(\s+)")


def strip_diacritics(s: str) -> str:
    return "".join(c for c in s if c not in DIAC)


@dataclass
class Word:
    surface: str
    output: str
    status: str           # certain | ambiguous | unknown
    variants: int = 1


@dataclass
class Diacritised:
    text: str
    words: list[Word] = field(default_factory=list)

    @property
    def uncertain(self) -> list[Word]:
        """The words worth a human's attention, in order."""
        return [w for w in self.words if w.status != "certain"]

    @property
    def coverage(self) -> float:
        real = [w for w in self.words if w.status != "punct"]
        if not real:
            return 1.0
        return sum(w.status == "certain" for w in real) / len(real)


class Diacritiser:
    def __init__(self, lexicon_path: str | Path):
        blob = json.loads(Path(lexicon_path).read_text())
        self.meta = blob.get("meta", {})
        self._w: dict[str, list] = blob["words"]

    @property
    def licence(self) -> str:
        """The lexicon's licence — NOT the engine's. Callers shipping commercially
        must check this; a GPL-2.0 lexicon cannot go inside a proprietary product."""
        return self.meta.get("licence", "unknown")

    def word(self, token: str) -> Word:
        sk = strip_diacritics(token)
        hit = self._w.get(sk)
        if not hit:
            return Word(token, token, "unknown")
        form, _count, variants = hit
        return Word(token, form, "certain" if variants == 1 else "ambiguous", variants)

    def __call__(self, text: str) -> Diacritised:
        out, seen = [], []
        for piece in _TOKEN.split(text):
            if not piece or piece.isspace():
                out.append(piece)
                continue
            # keep trailing punctuation out of the lookup
            m = re.match(r"^(.*?)([^\w؀-ۿ]*)$", piece, re.S)
            core, tail = (m.group(1), m.group(2)) if m else (piece, "")
            if not core:
                out.append(piece)
                continue
            w = self.word(core)
            seen.append(w)
            out.append(w.output + tail)
        return Diacritised("".join(out), seen)

"""The pronunciation lexicon: how a token that is not a number should be said.

Numbers are the measured failure, but they are not the only thing a TTS engine
reads wrong. `AED`, `km²`, `%`, `ص.ب`, `CEO` are all tokens an Arabic voice either
spells out letter by letter, says in English, or skips. A lexicon is the cheap,
auditable, zero-latency fix, and unlike a model it can be corrected by the person
who heard the mistake.

Two rules hold this together:

1. **Whole tokens only.** A substring replacement turns `كم` (how much) inside
   `تراكم` into `تراكميلومتر`. Every entry is anchored on token boundaries.
2. **The caller's entries win.** `Lexicon.update()` overrides the built-ins rather
   than merging under them, because the caller is the one who heard the audio.

The built-in table is MIT and ours. It is deliberately small: a lexicon that
guesses is worse than one that admits it does not know the word.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

#: Token classes, in the order they are applied. Symbols run first because they
#: are punctuation and cannot be caught by a word-boundary match.
CLASSES = ("symbols", "units", "currencies", "abbreviations", "acronyms")

# Python's \b is defined over [A-Za-z0-9_], so it does NOT fire between an Arabic
# letter and a Latin one - `SMSك` would match `SMS`. The boundary is therefore
# spelled out as "not a letter, in any script".
#
# Deliberately a LETTER class and not a word class: a digit beside a unit is
# normal writing (`12km`, `40°C`), while a letter beside one means the key is part
# of a longer word (`تراكم`, `AIRPORT`) and must not be touched.
_LETTER = r"[^\W\d_]"


_IS_LETTER = re.compile(rf"^{_LETTER}$")


def _entry_pattern(key: str) -> re.Pattern[str]:
    """Anchor each side only where the key actually ends in a word character.

    `%` and `°` are punctuation and need no boundary at all. `km` and `AI` do,
    or `تراكم` and `AIRPORT` get rewritten. Deciding it per side from the key
    itself covers `°C` and `ص.ب` without a special case for each.
    """
    left = rf"(?<!{_LETTER})" if _IS_LETTER.match(key[0]) else ""
    right = rf"(?!{_LETTER})" if _IS_LETTER.match(key[-1]) else ""
    return re.compile(left + re.escape(key) + right)


@dataclass
class Lexicon:
    """A token -> spoken-form map, grouped by class and licence-tagged."""

    entries: dict[str, str] = field(default_factory=dict)
    meta: dict = field(default_factory=dict)
    _compiled: list[tuple[re.Pattern[str], str]] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        self._compile()

    def _compile(self) -> None:
        # Longest key first: `km/h` must beat `km`, `°C` must beat `°`.
        self._compiled = [
            (_entry_pattern(k), v)
            for k, v in sorted(self.entries.items(), key=lambda kv: -len(kv[0]))
        ]

    @property
    def licence(self) -> str:
        """The lexicon's licence, not the engine's. A lexicon built from a
        copyleft corpus cannot go inside a proprietary product - see the
        diacritics lexicon note in the README."""
        return self.meta.get("licence", "unknown")

    def update(self, entries: dict[str, str]) -> "Lexicon":
        """Add or override entries. Caller wins. Returns self, so it chains."""
        self.entries.update(entries)
        self._compile()
        return self

    def apply(self, text: str) -> str:
        """Rewrite every known token, then collapse whitespace.

        Replacements are padded because Arabic letters are word characters to
        `re`: `40°C` -> `40درجة` leaves no boundary, and the number rule that runs
        next then fails to see a number at all. Padding and collapsing is cheaper
        and safer than teaching every later pattern about it.
        """
        for pattern, spoken in self._compiled:
            text = pattern.sub(f" {spoken.strip()} ", text)
        return re.sub(r"[ \t]{2,}", " ", text).strip(" \t") if self._compiled else text

    @classmethod
    def from_dict(cls, blob: dict, classes: tuple[str, ...] = CLASSES) -> "Lexicon":
        entries: dict[str, str] = {}
        for name in classes:
            entries.update(blob.get(name, {}))
        return cls(entries=entries, meta=blob.get("meta", {}))

    @classmethod
    def load(cls, path: str | Path, classes: tuple[str, ...] = CLASSES) -> "Lexicon":
        """Load a lexicon JSON from disk - your own terms, your own licence."""
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")), classes)

    @classmethod
    def builtin(cls, classes: tuple[str, ...] = CLASSES) -> "Lexicon":
        """The lexicon shipped with the package. MIT."""
        blob = json.loads(
            resources.files(__package__).joinpath("data/pronunciation.json")
            .read_text(encoding="utf-8")
        )
        return cls.from_dict(blob, classes)

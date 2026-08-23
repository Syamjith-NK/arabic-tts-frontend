"""arabic-tts-frontend - make Arabic text speakable before it reaches a TTS engine.

Shipping Arabic TTS engines do not read numbers. Measured on 45 sentences through
Fish Audio: 23/45 numbers survived synthesis intact, and on Arabic-Indic digits
(١٢٣) 0/15 did. Putting this package in front of the same engine took that to
37/45 and 12/15. The measurement, the harness and the scorer are all in the repo.

    from arabic_tts_frontend import VoiceFrontEnd
    fe = VoiceFrontEnd()
    fe.prepare("موعدنا 08:30 والتكلفة AED 1,250.50").spoken
"""
from .lexicon import CLASSES, Lexicon
from .normalize import Normalised, normalise
from .numbers import digit_by_digit, fold_digits, verbalise
from .parse import recovered, recovered_multi, words_to_values
from .pipeline import Prepared, VoiceFrontEnd

__version__ = "0.1.0"
__all__ = [
    "CLASSES", "Lexicon", "Normalised", "Prepared", "VoiceFrontEnd",
    "digit_by_digit", "fold_digits", "normalise", "recovered", "recovered_multi",
    "verbalise", "words_to_values", "__version__",
]


def __getattr__(name: str):
    # Imported lazily: it is the only module that needs an external lexicon file,
    # and most callers never diacritise.
    if name in ("Diacritiser", "Diacritised", "Word"):
        from . import diacritics
        return getattr(diacritics, name)
    raise AttributeError(name)

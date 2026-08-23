"""`arabic-tts-frontend` - normalise Arabic text on the command line.

Reads arguments, or stdin when there are none, so it drops into a shell pipeline
in front of whatever calls your TTS engine.
"""
from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .lexicon import Lexicon
from .pipeline import VoiceFrontEnd


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="arabic-tts-frontend",
        description="Turn Arabic text into speech-ready Arabic text.")
    ap.add_argument("text", nargs="*", help="text to normalise (default: read stdin)")
    ap.add_argument("--json", action="store_true",
                    help="emit original, spoken and the rules that fired")
    ap.add_argument("--lexicon", metavar="FILE",
                    help="pronunciation lexicon JSON; overrides the built-in entries")
    ap.add_argument("--diacritics", metavar="FILE",
                    help="diacritisation lexicon JSON; off unless given")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    lex = Lexicon.builtin()
    if args.lexicon:
        # Caller wins - they are the one who heard the audio.
        lex.update(Lexicon.load(args.lexicon).entries)
    fe = VoiceFrontEnd(diacritics_lexicon=args.diacritics, lexicon=lex)

    lines = [" ".join(args.text)] if args.text else [l.rstrip("\n") for l in sys.stdin]
    for line in lines:
        if not line.strip():
            print()
            continue
        p = fe.prepare(line)
        if args.json:
            out = {"original": p.original, "spoken": p.spoken, "applied": p.applied}
            if p.uncertain:
                out["uncertain"] = [w.surface for w in p.uncertain]
                out["coverage"] = round(p.coverage, 4)
            print(json.dumps(out, ensure_ascii=False))
        else:
            print(p.spoken)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

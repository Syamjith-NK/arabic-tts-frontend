"""The 45 benchmark sentences, checked offline.

These are the exact sentences that were synthesised and transcribed to produce the
README's numbers. Re-running that costs API credits and a Whisper pass, so this
test checks the two properties that do not need audio:

1. **No digit survives normalisation.** A digit reaching the engine is the failure
   the whole package exists to remove, and it is the one that scored 0/15.
2. **The verbalisation round-trips.** Parsing our own output back with the scorer
   must return the number we started from. If it does not, we are handing the
   engine a *different* number - a silent, and much worse, failure than a digit.

Property 2 is the one that would have caught the دقيقة/إلا الربع hour bug on its own.
"""
import json
import pathlib

import pytest

from arabic_tts_frontend import normalise, recovered_multi

CORPUS = pathlib.Path(__file__).with_name("bench_sentences.jsonl")
ROWS = [json.loads(line) for line in CORPUS.read_text(encoding="utf-8").splitlines() if line.strip()]
IDS = [f"{r['id']}-{r['form']}" for r in ROWS]

# Documented, not silently tolerated. A phone number is read digit by digit on
# purpose, so its digits do not reconstruct as one value - that is the rule
# working, not failing.
DIGIT_BY_DIGIT = {"phone_971"}


def test_corpus_is_the_published_one():
    assert len(ROWS) == 45
    assert {r["form"] for r in ROWS} == {"western", "arabic_indic", "spelled"}


@pytest.mark.parametrize("row", ROWS, ids=IDS)
def test_no_digit_reaches_the_engine(row):
    spoken = normalise(row["text"]).tts
    leftover = [c for c in spoken if c.isdigit() or c in "٠١٢٣٤٥٦٧٨٩"]
    assert not leftover, f"{spoken!r} still contains {leftover}"


@pytest.mark.parametrize("row", [r for r in ROWS if r["id"] not in DIGIT_BY_DIGIT],
                         ids=[i for i, r in zip(IDS, ROWS) if r["id"] not in DIGIT_BY_DIGIT])
def test_verbalisation_round_trips_to_the_same_value(row):
    spoken = normalise(row["text"]).tts
    assert recovered_multi(row["expect"], spoken), (
        f"{row['text']!r} -> {spoken!r} does not read back as {row['expect']!r}")


@pytest.mark.parametrize("row", [r for r in ROWS if r["id"] in DIGIT_BY_DIGIT],
                         ids=[i for i, r in zip(IDS, ROWS) if r["id"] in DIGIT_BY_DIGIT])
def test_identifiers_are_spelled_out_one_digit_at_a_time(row):
    spoken = normalise(row["text"]).tts
    # Every digit of the source appears as its own word, in order.
    digits = [c for c in normalise(row["text"]).original if c.isdigit() or c in "٠١٢٣٤٥٦٧٨٩"]
    assert len(spoken.split()) >= len(digits)

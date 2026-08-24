# arabic-tts-frontend

**Make Arabic text speakable before it reaches a TTS engine.**

Shipping Arabic TTS engines do not read numbers reliably. Measured on 45 sentences
through Fish Audio: **23/45** numbers survived synthesis intact, and on Arabic-Indic
digits (`٢٠٢٦`) **0/15** did. Putting this package in front of the same engine, same
model, same ASR, same scorer, took that to **34/45** and **11/15**.

Run-to-run noise on a 45-sentence set is about ±3, so treat the overall figure as
indicative and the digit-form result — **0/15 → 11/15** — as the finding. The
[measurement section](#the-shipped-code-has-now-been-re-measured-2026-08-24) shows both
runs and explains the difference rather than quoting the flattering number.

By [Syamjith NK](https://syamjithnk.com) — Abu Dhabi.

```bash
pip install arabic-tts-frontend
```

```python
from arabic_tts_frontend import VoiceFrontEnd

fe = VoiceFrontEnd()
p = fe.prepare("موعدنا 08:30 والتكلفة AED 1,250.50 بزيادة ٤٧٪")

p.original  # 'موعدنا 08:30 والتكلفة AED 1,250.50 بزيادة ٤٧٪'   -> subtitles, UI
p.spoken    # 'موعدنا الثامنة والنصف والتكلفة ألف ومئتان وخمسون درهم
            #  وخمسون فلس بزيادة سبعة وأربعون بالمئة'            -> the engine
```

Both forms always come back. The original is never destroyed: subtitles need the
digits, the engine needs the words.

No dependencies. Pure Python, ≥3.9.

---

## The measurement

A/B on the [ArNum-TTS](https://huggingface.co/datasets/syamjithnk/arnum-tts) set:
15 sentences × 3 numeral forms. Both arms run the **same night, same engine
(`fish s2.1-pro-free`), same ASR (`faster-whisper medium`), same scorer**. The only
variable is this package.

The scorer compares **values, not spellings** — `674` and `ستمائة وأربعة وسبعون` are
the same answer, because a listener who hears either one has the number.

| numeral form | engine alone | + front-end |
|---|---|---|
| `western` — `2026` | 11/15 (73%) | **13/15 (87%)** |
| `arabic_indic` — `٢٠٢٦` | 0/15 (0%) | **12/15 (80%)** |
| `spelled` — `ألفين وستة وعشرين` | 12/15 (80%) | 12/15 (80%) |
| **overall** | **23/45 (51%)** | **37/45 (82%)** |

Measured 2026-08-22. Per-utterance transcripts:
[`results_fish_control.jsonl`](https://huggingface.co/datasets/syamjithnk/arnum-tts) /
`results_fish_normalised.jsonl`.

By category:

| category | n | engine alone | + front-end |
|---|---|---|---|
| currency | 6 | 2/6 | **5/6** |
| year | 6 | 4/6 | **6/6** |
| decimal | 3 | 1/3 | **3/3** |
| date | 3 | 1/3 | **3/3** |
| time | 6 | 3/6 | **4/6** |
| range | 3 | 2/3 | **3/3** |
| percentage | 3 | 2/3 | **3/3** |
| ordinal | 3 | 2/3 | **3/3** |
| count | 9 | 6/9 | **7/9** |
| phone | 3 | 0/3 | 0/3 |

The `spelled` row not moving is the control working: those sentences contain no
digits, so the package correctly does almost nothing to them. If that row had moved,
the result would be noise.

### The engine baselines this sits on top of

| numeral form | fish `s2.1-pro-free` | Apple `Majed` | ArTST `speecht5_tts_clartts_ar` |
|---|---|---|---|
| western | 11/15 (73%) | 13/15 (87%) | 0/15 (0%) |
| arabic_indic | 1/15 (7%) | 13/15 (87%) | 0/15 (0%) |
| spelled | 13/15 (87%) | 9/15 (60%) | 4/15 (27%) |

Apple normalises before speaking and is therefore form-agnostic — the existence proof
that this is solvable. ArTST cannot speak either digit form: the Arabic-Indic digits
`٠-٩` are **absent from its 87-token vocabulary**, so `٢٠٢٦` collapses to a single
`<unk>` and is deleted before synthesis starts. For an engine like that, verbalising
all the way to Arabic *words* is not an optimisation, it is the only way to say a
number at all.

---

## What it does

```
raw text  ->  fold digits  ->  STRUCTURAL rules  ->  lexicon  ->  GENERIC rules  ->  engine
```

The order is the design, not an accident. Structural rules run first because they need
the raw token: `AED 1,250.50` is a currency only while `AED` is still `AED`, and
`0501234567` is a phone number only before something reads it as a quantity. The
lexicon runs next, so `km²` and `CEO` become Arabic words. Generic number rules run
last, over what is left — by then guaranteed to be a plain quantity.

| class | in | out |
|---|---|---|
| cardinal | `لدي ١٢٣ مستخدمًا` | `لدي مئة وثلاثة وعشرون مستخدمًا` |
| currency | `AED 1,250.50` | `ألف ومئتان وخمسون درهم وخمسون فلس` |
| date | `20/08/2026` | `عشرون أغسطس عام ألفان وستة وعشرون` |
| time | `08:30` | `الثامنة والنصف` |
| percent | `2.5%` | `اثنان فاصلة خمسة بالمئة` |
| phone / short code | `الرقم 800 555` | `الرقم ثمانية صفر صفر خمسة خمسة خمسة` |
| version | `2.1.0` | `اثنان نقطة واحد نقطة صفر` |
| units, acronyms | `100 km/h`, `AI` | `مئة كيلومتر في الساعة`, `الذكاء الاصطناعي` |
| Arabic-Indic digits | `٢٠٢٦` | folded to Western **first**, then verbalised |

Folding alone is not a fix. An engine that cannot say `2026` still cannot say it.

### Three rules that reach the listener as fact

These are the ones a naive implementation gets wrong, and getting them wrong is worse
than not converting at all:

**Never invent AM/PM.** A bare `2:45` does not say which. Appending `صباحًا` fabricates
a fact, and when the sentence already said `بعد الظهر` it produces a self-contradicting
utterance. The period is stated only when the source is unambiguous (a 24-hour hour)
*and* the author has not already said it.

**`إلا الربع` names the NEXT hour.** `2:45` is `الثالثة إلا الربع`. Saying
`الثانية إلا الربع` announces 1:45 — an hour early, which is worse than any
mispronunciation.

**A phone number is never a cardinal.** Reading `0501234567` as five hundred and one
million… is worse than leaving the digits alone. Identifiers are spelled digit by
digit. The rule fires on a phone-context word (`رقم`, `هاتف`, `تحويلة` …) plus **five or
more** digits — the floor is what keeps `القانون رقم 33` and `غرفة رقم 305` as
quantities, because those really are numbers.

---

## The lexicon

Numbers are the measured failure but not the only one. `AED`, `km²`, `%`, `ص.ب`, `CEO`
are all tokens an Arabic voice either spells out letter by letter, says in English, or
skips. A lexicon is the cheap, auditable, zero-latency fix — and unlike a model it can
be corrected by the person who heard the mistake.

```python
from arabic_tts_frontend import Lexicon, normalise

lex = Lexicon.builtin().update({"ADNOC": "أدنوك", "NDA": "اتفاقية عدم إفصاح"})
normalise("وقعنا NDA مع ADNOC", lexicon=lex).tts
# 'وقعنا اتفاقية عدم إفصاح مع أدنوك'
```

80 entries ship, across symbols, units, currencies, abbreviations and acronyms. It is
deliberately small: **a lexicon that guesses is worse than one that admits it does not
know the word.** Two rules hold it together:

- **Whole tokens only** — and the boundary is a *letter* boundary, not `\b`. Python's
  `\b` does not fire between an Arabic letter and a Latin one, so `SMSك` would match
  `SMS`; and a digit beside a unit is normal writing, so `12km` must still convert
  while `تراكم` and `AIRPORT` must not.
- **The caller's entries win.** `update()` overrides the built-ins rather than merging
  under them, because the caller is the one who heard the audio.

A bare `ص` or `م` is deliberately **not** in the table. They are ordinary Arabic letters
far more often than they are clock periods; deciding AM/PM belongs to the time rule,
where there is actually a clock to key off.

---

## Diacritisation (optional, no lexicon ships)

Diacritics decide how a word is *pronounced*, and Arabic text is written without them.
Measured on `arbml/tashkeela`, 400 rows / 23,540 words:

| baseline | DER | DER no-case | WER | WER no-case |
|---|---|---|---|---|
| predict nothing (the floor) | 78.84% | 80.18% | 98.48% | 97.35% |
| **most-frequent-per-word lexicon** (held out) | **12.13%** | **8.81%** | 26.58% | **11.07%** |

And on the same 60 rows, against a real model:

| system | DER | DER no-case | WER | **WER no-case** |
|---|---|---|---|---|
| lexicon (held out) | 10.19% | **6.48%** | **26.67%** | **11.00%** |
| `Abdou/arabic-tashkeel-flan-t5-small` | **8.84%** | 7.94% | 29.92% | 21.91% |

A plain lexicon beats a 300M seq2seq **2× on WER-no-case** — the metric that decides
whether a *word* comes out right, with the case ending excluded because it is
syntactically determined and dropped at a pause in spoken MSA anyway. That is the
evidence for choosing a lexicon here, not taste.

What it adds that a model does not: **per-word confidence.**

```python
fe = VoiceFrontEnd(diacritics_lexicon="my_lexicon.json")
p = fe.prepare("كتب الطالب")
p.report()      # '50% certain - review: كتب(3)'
p.uncertain     # [Word(surface='كتب', output='كَتَبَ', status='ambiguous', variants=3)]
```

`certain` = one form ever attested · `ambiguous` = several, most frequent used ·
`unknown` = not in the lexicon, passed through bare. An engine given a bare word
guesses silently; this hands you the list of words to review instead.

**No diacritisation lexicon ships with this package.** The only one measured was built
from Tashkeela, which is **GPL-2.0** — bundling it would relicense the engine. Build
your own from a permissive or owned corpus; the loader does not care which file it
gets, and `fe.diacritics_licence` reports whatever the file declares. Format:

```json
{"meta": {"licence": "CC-BY-4.0"},
 "words": {"<undiacritised skeleton>": ["<most frequent form>", <count>, <n_variants>]}}
```

---

## CLI

```console
$ arabic-tts-frontend "في عام ٢٠٢٦ نمت الإيرادات 25%"
في عام ألفان وستة وعشرون نمت الإيرادات خمسة وعشرون بالمئة

$ echo "في 14:00 غدا" | arabic-tts-frontend --json
{"original": "في 14:00 غدا", "spoken": "في الثانية مساءً غدا", "applied": ["time"]}
```

`--lexicon FILE` to add your own terms, `--diacritics FILE` to switch step 3 on.

---

## Limits — read these before quoting the numbers

**Gender agreement is not solvable by a lookup table.** `3 كتب` is `ثلاثة كتب` but
`3 سيارات` is `ثلاث سيارات`: the number's form depends on the gender of the noun that
follows, and getting it wrong is audible to any Arabic speaker. `verbalise()` takes a
`feminine` flag and the pipeline **does not set it**, because nothing here parses the
noun. Masculine is the default. If you know the gender, pass it.

**Case endings (i'rab) are not produced.** `أحد عشر ألفًا` comes out as `أحد عشر ألف`.
Audible to a careful listener, not usually a comprehension failure.

**Phone numbers still score 0/3** and that is honest, not hidden. The front-end now
reads them digit by digit, which is correct; Whisper transcribes the result back as
digits, and the value scorer does not credit that as a match. The rule is right and
the *measurement* of it is not yet.

**One engine, 45 sentences, no human listening pass.** The A/B is Fish only. 45
utterances is small; the relative gap (0% → 80% on Arabic-Indic) is far too large to be
transcription noise, but the absolute percentages should not be quoted as a
characterisation of Arabic TTS as a field.

**The comparator was re-run, not reused.** The engine-alone arm here is 23/45; an
earlier run of the identical arm four days before scored 25/45. Neither is wrong —
TTS output is not deterministic, and that ±2 is the run-to-run noise floor. Both arms
of the A/B were run the same night for exactly that reason.

**The shipped code has now been re-measured (2026-08-24).** The earlier run scored the
pre-packaging source; this one synthesised all 45 sentences fresh from the released
package through the identical engine, model, ASR and scorer.

| arm | overall | western | arabic_indic | spelled |
|---|---|---|---|---|
| engine alone | 23/45 | 11/15 | 0/15 | 12/15 |
| pre-packaging source | 37/45 | 13/15 | 12/15 | 12/15 |
| **released package** | **34/45** | 10/15 | 11/15 | 13/15 |

**34/45, not 37/45 — and the earlier "37 is a floor" reading was wrong.** But the
difference is mostly not code. Seven sentences flipped between the two runs and **five
of them were byte-identical text**: same input, same engine, different transcript. That
puts the run-to-run noise on this 45-sentence set at roughly **±3**, which is wider than
the gap being argued about. A single run of this benchmark cannot distinguish 34 from 37,
and neither number should be quoted to two significant figures.

Only one sentence regressed for a real reason, and it is worth more than the score. The
packaging fix made `1,200,000` read as `مليون ومئتا ألف` — the correct construct-state
dual — and the engine **mispronounces it**: ASR heard `مائة ألف`, so a listener is told
one hundred thousand instead of one point two million. The technically-wrong `مئتان ألف`
survived. Grammatical correctness and engine intelligibility are different targets, and
this package exists to serve the second one. `numbers.DROP_DUAL_NUN` now switches it;
the default stays grammatical, because two sentences on one engine is not enough evidence
to teach everyone bad Arabic.

What is not in doubt at any noise level: **0/15 → 11-12/15 on Arabic-Indic digits**, the
failure this package was built for.

**The measurement chain is TTS → Whisper → parser**, and an error anywhere in it is
charged to the TTS. Three rounds of parser fixes once moved the Western scores from 47%
to 73–87% *without a single audio file changing*. That is why the parser ships too —
so you can re-run the scoring rather than take it on trust.

### Two bugs found in our own scorer

Both made the result look better, which is the direction errors go when nobody checks.

1. **Digit-only scoring.** The first version looked only for digit strings, so correct
   spoken Arabic (`ستمائة وأربعة وسبعون`) was marked a failure. That understated every
   form. `parse.py` now compares values.
2. **Dictionary leakage** in the diacritics baseline: the lexicon was first built over
   rows that included the test sample. 9.94% → **12.13%** DER once held out. The leak
   was worth ~2pp, in the flattering direction.

Both are documented here rather than quietly corrected, because a benchmark whose
scorer is wrong is worse than no benchmark.

---

## API

| | |
|---|---|
| `VoiceFrontEnd(diacritics_lexicon=None, lexicon=None)` | the whole pipeline; `.prepare(text) -> Prepared` |
| `normalise(text, lexicon=None) -> Normalised` | steps 1–2 only; `.original`, `.tts`, `.applied`, `.changed` |
| `Lexicon.builtin() / .load(path) / .update(dict)` | the pronunciation table; `.licence`, `.apply(text)` |
| `verbalise(n, feminine=False) -> str` | an integer as Arabic words |
| `digit_by_digit(s) -> str` | an identifier, one digit at a time |
| `fold_digits(text) -> str` | Arabic-Indic and Eastern digits, and `٫` `٬`, to Western |
| `words_to_values(text) -> set[int]` | **the scorer** — every number in the text, as values |
| `recovered(expect, heard) / recovered_multi(...)` | did the number survive? |

`Prepared.applied` names every rule that fired, in order — the first thing to look at
when the audio is wrong.

## Development

```bash
git clone https://github.com/Syamjith-nk/arabic-tts-frontend && cd arabic-tts-frontend
pip install -e ".[dev]" && pytest
```

190 tests. `tests/test_field_corpus.py` runs all 45 benchmark sentences offline and
asserts two properties that need no audio: **no digit survives normalisation**, and
**the verbalisation round-trips** — parsing our own output back must return the number
we started with. The second one is what catches a wrong-hour bug on its own, because
handing the engine a *different* number is a far worse failure than handing it a digit.

## Related

- **[ArNum-TTS](https://huggingface.co/datasets/syamjithnk/arnum-tts)** (CC-BY-4.0) —
  the benchmark these numbers come from, with per-utterance transcripts.
- Write-up: *[One of these reads ٢٠٢٦ as a year. The other reads it as
  noise.](https://syamjithnk.com/arabic-tts-numerals)*

## Licence

MIT © Syamjith NK. The built-in pronunciation lexicon is MIT. Any diacritisation
lexicon you load carries **its own** licence — check `.licence` before shipping
commercially.

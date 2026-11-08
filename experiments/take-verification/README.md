# Take verification: can Whisper catch a recording that says the wrong thing?

Now and then a line in a loop is spoken slightly wrong: a sound swapped, a word changed, something
added. It is rare (the owner heard it perhaps once in October, and a few times before), but a loop
cannot be recorded again from the interface, while a word clip or a story passage can ("Record
again"). The idea under test: transcribe each new recording with a small multilingual Whisper, compare
it with the text that was asked for, and record it once more if they clearly disagree.

The filter has to be **precise** before it is sensitive. A false alarm costs a second model call and
the time it takes, and the owner's lines are spoken with emotion on purpose ("Speak surprised, but
clearly, slowly, with a slightly lower pitch."), which is exactly what pulls a transcript away from the
text without anything being wrong. The owner's estimate was about three bad recordings in the whole
store, and that was the target.

**Status:** closed 8 Nov 2026. **Settled:** record a loop line again, once, when Whisper hears a word
of its *direction* around the text — the direction read out, or one word of it said after the text.
Nothing else. It fired on 3 of 2,032 loop lines, all three judged wrong by the owner, with every
model; Whisper base on CTranslate2 is enough, at 2.0 s a take on the NAS. Built into the
take route ([`docs/features/loops.md`](../../docs/features/loops.md) §2.4), where it runs while the
next take is recorded.

## What was listened to

Every recording the server holds, pulled read-only (`pull.py`):

| Kind | Clips | Where the expected text comes from |
| --- | --- | --- |
| Loop lines (takes) | 2,032 | The call log: each `pronounce-take … result=recorded` line names the text, language, direction and take, and its `bytes=` is the size of the FLAC stored. The store sets the file's mtime and a cache hit does not rewrite it, so a line joins the one file of its size written just before it: 2,032 joined, none ambiguous; 113 lines whose file is gone, 405 files with no line (story masters and takes from before the log carried the text) |
| Word pronunciations | 25 | The `pronunciations` row: the text actually spoken |
| Story passages | 388 | `story_parts.audio_segments`: one file per passage, with its text and direction |

Loop lines are short — median 9 characters, longest 99 — which is where Whisper is least reliable, and
most are Gemini 3.1 Flash TTS, read under LexiBeat's director note. Languages: English 1,028, Spanish
882, Russian 117, Chinese 5.

## The signals (`check.py`)

Whisper (transformers, the engine the server image already carries) is told the language and decodes
greedily. Per clip, for **base**, **small** and **large-v3-turbo** (all multilingual; distil-whisper is
English-only):

- `cer`, `wer`: its transcript against the text, both folded (case, accents, punctuation, ё);
- `gap`: the mean per-token log-probability of Whisper's own transcript minus that of the expected
  text, both teacher-forced through the same decoder over one encoder pass. **The precision guard**:
  when the asked-for text is about as likely as Whisper's guess, the mismatch is Whisper's. The expected
  text is scored in the surface forms Whisper writes (as stored, capitalised, with a full stop), since a
  bare headword "las gracias" heard as "Las gracias." otherwise opens a gap of 1.0 from casing alone;
- `twice` and `instruction`: the text came back doubled, or words of the direction came back —
  `expressive-voice`'s two findings, its code copied;
- `dz`: seconds per expected character as a robust z-score within kind and language.

The rule tried (`sweep.py`): `twice OR instruction OR (cer > τc AND gap > τg)`.

**Wiring check first.** On the 232 takes of [`expressive-voice`](../expressive-voice/README.md), whose
three faults were found by ear (f12's tag read aloud, a01 and a02 said twice), small put exactly those
three at the top by CER (1.24, 1.09, 1.08; the next is 0.17) and raised both structural flags. The same
run shows what the guard is for: «¿Qué talla necesitas?» heard as «tasha» — the Argentine «ll», said
right — has a gap of −0.04.

## What the owner ruled

82 clips judged on the iPad (`review.py`): everything the first rule raised at a middle threshold for
small and base, the duration outliers, six exclamation cases and twelve random controls. 75 right, 6
wrong, 1 unsure (Chinese). The ruling that reshaped the rule:

- **Emotion is the point.** An exclamation around the word («Pfff, bancarse.», «¡Aah! ¡Quejarse!»,
  «Oh, frivolous.»), a laugh, a word stretched or shouted («R-RIGHT!», «REACH!») — all right, though
  they are exactly what pulls a transcript away from its text.
- **Wrong, and keep anyway:** «clumsy» said as laughter only, «hit» as a pained «uhh» — a loop says
  each line three times, and one take that only laughs adds charm.
- **Wrong, record again:** the direction spoken. «cough», asked to sound "annoyed and raspy, seeking
  relief from irritation in the throat", said «Seek relief from irritation in the throat» in one take
  and «I need a congestion relief» in another; «to provide», asked as "a helpful host offering more
  food", said «to provide more».

One more fault turned up outside loops: a story passage cut as the fragment «Sin mostrar ningún
temor,» came back as eleven seconds of speech, the voice **inventing** the rest of the sentence («el
joven luchó contra aquellos seres…», which is in no story). Its duration was the outlier of the whole
store (z = 10.1; next 4.8), so a free duration check could catch it — one case, a lead and not a
result ([`docs/plans/issues.md`](../../docs/plans/issues.md)).

## Results

**The rule** (`sweep.leak`): words Whisper hears *outside the text's own stretch* that are words of the
direction sent (three letters or more, not a stop word, not in the text; plus the accent words). The
alignment (`check.contained`) needs no list of exclamations, so it works in any language: an
exclamation is never in the direction, and «more» and «relief» were.

| Model | Clips | Fired | Judged wrong | Judged right |
| --- | --- | --- | --- | --- |
| base | 2,445 | 3 | 3 | 0 |
| small | 2,445 | 3 | 3 | 0 |
| large-v3-turbo | 382 (the cards and 300 random lines) | 3 | 3 | 0 |

All three are loop lines; it fires on no word clip and no story passage. Precision is fully measured —
every clip it fires on was judged. Recall is not: at three in two thousand, a random sample large
enough to find a miss is not worth an evening's listening; the integration logs every firing instead.

**The first rule, rejected** (`report.md` has the grids): `twice OR instruction OR (cer_inner > τc AND
gap > τg)`. At its best cell small raised 5 lines with 4 judged wrong, but two of those four are the
laughter and the «uhh» the owner keeps, and below that cell every step adds emotional deliveries
judged right (precision 0.09–0.29). It also needs the teacher-forced score, which is the expensive
engine. What it was good for: finding the faults to look at.

**What else was learnt:**
- *Base merges a repetition.* On `expressive-voice`'s takes it heard «Decepcionar. Decepcionar.» once
  (small and turbo caught both doublings and the tag read aloud, and nothing else). No Acervo take
  was doubled, and a loop repeats its lines anyway, so the rule leaves doubling out.
- *Whisper writes Chinese in traditional characters* (圖書館 for 图书馆): folded with OpenCC (Apache-2.0)
  before comparing.
- *The interjections are the voice, not the transcriber:* small, base and turbo hear the same «Pfff»,
  and turbo (the strongest) heard the instruction read out exactly as base did.

### Cost, on the NAS (AMD Ryzen R1600, inside the acervo-server image)

Median seconds per clip, 4 threads, 100 clips (80 loop lines of ~2 s, 10 words, 10 passages of ~7.5 s):

| Engine | base | small |
| --- | --- | --- |
| CTranslate2 (faster-whisper, int8) | **2.0** | 7.0 |
| transformers (the image's own) | 4.1 | 15.5 |

Whisper encodes a padded 30-second window whatever the clip's length, so a one-word take costs what a
passage does. The settled rule needs only a transcript, so CTranslate2 base is enough. Turbo was
stopped part-way — small already rules out anything larger. Two seconds is too much where the owner
waits (a word, a story passage: "Record again" covers those) and acceptable for a loop, which renders
unattended; overlapping the check with the next take's synthesis hides most of it (the plan).

## Commands

```bash
uv venv experiments/take-verification/.venv --python 3.12
uv pip install --python experiments/take-verification/.venv/bin/python faster-whisper transformers torch jiwer soundfile numpy opencc-python-reimplemented

# Everything below runs from experiments/take-verification/.
.venv/bin/python pull.py --host HOST --root DEPLOYMENT_ROOT   # read-only; into out/
.venv/bin/python manifest.py
.venv/bin/python check.py --model small                        # and base; resumable
.venv/bin/python check.py --model small --rescore              # the span gap
.venv/bin/python sweep.py grid --model small
.venv/bin/python sweep.py listen                               # the cards
.venv/bin/python sweep.py rule --model base                     # the settled rule
.venv/bin/python check.py --model turbo --keys out/turbo-keys.txt
.venv/bin/python review.py --host "$(tailscale ip -4)" --port 8769
.venv/bin/python report.py

# The NAS's own CPU, in a throwaway container of the server image (sudo; weights fetched there)
NAS_ADMIN_PASSWORD=… ./nas_timing.sh HOST BUNDLE > results/nas-timing.jsonl
```

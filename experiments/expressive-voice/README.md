# Expressive voice: which settings for ElevenLabs?

ElevenLabs was added on 7 Nov 2026 and had never read anything for real. This experiment settles
the settings Acervo should use for it so that it works as well as it can: which model, and what to
send it for a feeling and for an accent. It does not compare ElevenLabs with Gemini. Gemini, with
about 200 real calls behind it, stays the default, and its takes are in the set only as a reference
for what a text should sound like.

Round 0, before this, was the owner's first listening:

- a long direction was read aloud;
- an accent tag alone made a word and a three-word phrase come out twice;
- only "feeling; accent from Argentina" behaved.

**Status:** closed 8 Nov 2026. Round 1 settled the model and the feeling tag; round 2's pairs settled
the accent. What Acervo sends is in `pronunciation/speak.Direction` and
[`docs/providers.md`](../../docs/providers.md) ("ElevenLabs: an expressive voice").

**Settled:**
- **Eleven v4** is the one model "Add the usual models" adds.
- **A feeling** goes as the short tag, with the accent: `surprised and amused; accent from Argentina`.
- **An accent alone** goes as `calm and natural; accent from Argentina`: heard as Argentine in 7 of 7
  pairs, and never doubled a text.
- **Never** the bare `accent from …` alone (it doubles one- and two-word texts), and never the
  variety by name (it moved the accent less, or not at all).

## Round 1: the set, sent the way Acervo sends it

### Systems: one voice each

| Id | Route | Model | Voice | Role |
|---|---|---|---|---|
| `v4` | ElevenLabs | `eleven_v4` | Sarah | Under test, with Acervo's tag and four ways of sending an accent alone |
| `v3` | ElevenLabs | `eleven_v3` | Sarah | Under test, with Acervo's tag only |
| `gemini` | `vertex`, Cloud TTS | `gemini-3.1-flash-tts-preview` | Achernar | Reference: what the server's expressive order reads every language with today |

Sarah, as in round 0; Acervo's own chooser would pick Bella, the first in the account's list. Gemini
was asked three times per item and take 1 is rated; all three are transcribed.

### The set (`set.json`)

43 items drawn with a fixed seed from a read-only pull of the owner's vocabulary.

| Group | Items | Text | Eleven v4 is sent | Eleven v3 is sent | Gemini is sent |
|---|---|---|---|---|---|
| feeling | 9 es-AR, 3 en-GB, 3 ru | Real examples with their stored `emotion`; the Russian ones are stored translations of English examples | `emotion; accent from Argentina` (Russian: the emotion) | the same | `acervo_pronounce_style` |
| story | 4 es-AR | Passages the server cut, with their direction | the direction plus the accent | not recorded (credits) | `acervo_pronounce_story` |
| accent | 7 lengths × es-AR, es-ES | The same 7 texts of 1 to 16 words in both varieties | four variants, below | not recorded (credits) | `acervo_pronounce_accent` |
| words | 6 es-AR, 2 en-GB, 2 ru | Headwords | nothing, as Acervo sends | nothing | `acervo_pronounce_accent` (Russian: nothing) |

The accent alone, on Eleven v4:

| Variant | Tag |
|---|---|
| `current` | `accent from Argentina` / `accent from Spain`: Acervo's form with the feeling left out |
| `calm` | `calm and natural; accent from …`: always a feeling |
| `named` | `Argentine Spanish accent` / `Castilian Spanish accent` |
| `none` | no tag, Acervo's behaviour. ElevenLabs takes no region, so it is one request for both varieties, recorded once under es-AR |

Only 2 of the 7 accent texts hold «ll» or «y» before a vowel, the sound that makes Spanish audibly
Argentine; "decepcionar" sounds the same in every variety. A later accent test should choose its
texts for that sound.

**Credits.** 8,968 were left after round 0. The whole plan came to about 11,700 characters, so the
22-word accent text was dropped and v3 was given feelings and words only. The run spent 8,485
(`run.py bill` prints the arithmetic).

### What the ear found

The owner rated every take blind on the tablet: right (wrong / a slip / right), feeling (flat / some
/ carries it) and accent (not it / partly / clearly), with flags for a tag read aloud and a text said
twice, and a Best pick per item, which is the better of several good takes or none when nothing was
good. The full tables are in [`results/report.md`](results/report.md).

The 7 Spain items are left out of every conclusion: they asked for Castilian to be rated on its own,
which the owner, who speaks Argentine Spanish, cannot do. Round 2 uses Spain only as the other half
of a pair.

**The model: Eleven v4.**

| | Eleven v4 | Eleven v3 |
|---|---|---|
| Feeling carried, examples | 15 of 15 "carries it" | 14 of 15 "flat" |
| Words right (feeling, story, word takes) | 29 of 29 | 16 of 25, with 3 slips and 6 wrong (4 of them Spanish sentences) |
| A tag read aloud | 0 of 61 tagged takes, by ear and by Whisper | 1 (f12: "revealing someone's true intentions, accent from United Kingdom. His polite manner…") |

**The feeling: the short tag works.** Eleven v4 carried it on every example in all three languages;
story passages scored 2.0 of 3. A tag with no accent (the Russian examples) behaved the same.

**The accent: rated on its own, no tag was heard to carry it.** Round 2 showed this was the scale,
not the voice (below).

| Eleven v4, Argentine texts | With «ll»/«y» | Without |
|---|---|---|
| Examples and passages, `feeling; accent from Argentina` | 7 of 7 "not it" | 3 of 6 "not it" |
| Headwords, nothing sent | 4 of 4 "not it" | 2 of 2 "not it" |
| Accent alone, any of the four forms, **including no tag** | 2 of 2 "partly", every form | 1.6 to 2.0 of 3 |

Beside Gemini's takes, which were "clearly" Argentine on all 13 texts with «ll» or «y», every
ElevenLabs take was rated "partly" at best, and no tag did better than none.

**What a tag can break: a short text said twice.** The bare `accent from Argentina` said the 1- and
2-word texts twice ("Decepcionar. Decepcionar."), by ear and by Whisper, as in round 0: 4 of 4 short
texts across both rounds. `calm`, `named` and no tag doubled nothing at any length.

**Settled by round 1:** Eleven v4 as the one usual model, and the short tag for a feeling. Whether the
tag should carry the accent was left to round 2.

## Round 2: pairs, by ear (`pairs.py`)

Round 1 asked "is this Argentine?" take by take. A pair asks something the owner can answer for any
text: the same text read under two accents, and which one sounds Argentine (or British)? If a tag
moves ElevenLabs' accent, the take sent the Argentine tag is picked; if not, the two sound alike.

| Pairs | Language | Takes | Credits |
|---|---|---|---|
| 21 | Spanish | Eleven v4, round 1's accent texts under an Argentine and a Spain tag, three forms (`current`, `calm`, `named`) | none: already recorded |
| 7 | Spanish | Gemini's Argentine and Spain takes of the same texts | none |
| 2 | English | Eleven v4 (Sarah, an American voice) under `British English accent` and `American English accent`, f10 and f12 | 326 of the 356 left |
| 2 | English | Gemini under its accent sentence for `en-GB` and `en-US`, the same two | Vertex |

Gemini's pairs are the calibration: if they are not told apart, the contrast cannot be heard in those
texts and the pair says nothing about ElevenLabs. "Hogwash" was planned as a third English text and
did not fit the credits left. Whisper heard all eight English takes say exactly their text.

**Decision rule:** a tag form moves the accent when the tagged variety is picked in at least 6 of its
7 Spanish pairs (2 of 2 English), and Gemini's pairs reach the same. Otherwise the accent is dropped
from the ElevenLabs tag and only the feeling is sent.

### What the ear found (`results/pairs.md`)

| Eleven v4, sent | Pairs | Picked the Argentine / British one | The other | The same |
|---|---|---|---|---|
| `calm and natural; accent from …` | 7 | **7** | 0 | 0 |
| `accent from …` | 7 | **6** | 0 | 1 |
| `Argentine Spanish accent` / `Castilian Spanish accent` | 7 | 4 | 0 | 3 |
| `British English accent` / `American English accent` | 2 | 0 | 0 | 2 |
| Gemini, the calibration (Spanish 7, English 2) | 9 | 9 | 0 | 0 |

**The tag moves ElevenLabs' accent, in the "accent from …" form.** The Spain-tagged take was never
picked as Argentine, in any pair. The owner heard "a very lovely Argentinean accent", strikingly so
where the words have «ll». The named variety moved it less in Spanish and not at all in English.

So round 1's ratings undersold the accent: asked "is this Argentine?" take by take, beside Gemini, the
owner gave ElevenLabs "partly"; asked "which of these two?", the answer was plain. An accent is
judged in pairs.

Not heard yet: English in the "accent from …" form (the credits ran out), and the accent under a
feeling in pairs (round 1's feeling takes were rated on their own, like the rest of round 1). The
shipped feeling tag keeps the accent, the form that worked; it never doubled or was read aloud.

## Routes and allowances found on the way (`results/probe.json`)

- **Cloud TTS on Vertex has no 3.8 voices.** `gemini-3.8-flash-tts` and `gemini-3.8-flash-lite-tts`
  answer "The model … is not supported". 3.1 Flash preview, 2.5 Flash and 2.5 Pro TTS answer.
- **The `google-key` key does not reach the Gemini API.** It is restricted to Cloud TTS and Vision,
  and Google blocks it there.
- **The free Gemini API key allows 10 speech requests a day per model**, by Google's own 429 on 3.8
  Flash-Lite TTS. It cannot carry a vocabulary.

## Commands

```bash
# Round 1
.venv/bin/python experiments/expressive-voice/run.py set            # read-only pull, then the set
.venv/bin/python experiments/expressive-voice/run.py probe          # routes; --cap-calls N for the free cap
.venv/bin/python experiments/expressive-voice/run.py bill           # ElevenLabs characters; spends nothing
.venv/bin/python experiments/expressive-voice/run.py record         # resumable, nine minutes a pass
experiments/expressive-voice/.venv/bin/python experiments/expressive-voice/transcribe.py
.venv/bin/python experiments/expressive-voice/run.py blind          # loudness-matched letters, out/key.json
.venv/bin/python experiments/expressive-voice/review.py --host "$(tailscale ip -4)" --port 8767
.venv/bin/python experiments/expressive-voice/run.py report         # results/report.md

# Round 2
.venv/bin/python experiments/expressive-voice/pairs.py bill         # English credits; spends nothing
.venv/bin/python experiments/expressive-voice/pairs.py record
experiments/expressive-voice/.venv/bin/python experiments/expressive-voice/transcribe.py --pairs
.venv/bin/python experiments/expressive-voice/pairs.py blind        # out/pairs/key.json
.venv/bin/python experiments/expressive-voice/pairs.py serve --host "$(tailscale ip -4)" --port 8768
.venv/bin/python experiments/expressive-voice/pairs.py report       # results/pairs.md

# Whisper's own environment
uv venv experiments/expressive-voice/.venv --python 3.12
uv pip install --python experiments/expressive-voice/.venv/bin/python mlx-whisper jiwer
```

Every take goes through `pronunciation.speak.speak`, the function the server calls, pinned to one
pair and one voice. `out/` (audio, the pull, and the keys and labels until a report copies them) is
ignored; `set.json` and `results/` are committed.

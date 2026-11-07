# Expressive voice: does ElevenLabs follow a direction and an accent?

Gemini voices on Vertex have read the owner's examples and stories with a feeling for about a month,
over roughly a hundred real calls. ElevenLabs was added on 7 Nov 2026 with only round 0 behind it
([`docs/plans/expressive-voice.md`](../../docs/plans/expressive-voice.md)). In round 0:

- a long direction was read aloud;
- an accent tag alone made a word and a three-word phrase come out twice;
- only "feeling; accent from Argentina" behaved.

This round records one fixed set through ElevenLabs, sent the way Acervo sends it, with Gemini on
Vertex as the reference. It adds four ways of sending ElevenLabs an accent with no feeling. Whisper
listens back to every take, and the owner rates the takes blind on the tablet.

**Status:** recorded and transcribed on 7 Nov 2026; the owner's listening has not happened yet.

## Systems: one voice each

| Id | Route | Model | Voice | Why this one |
|---|---|---|---|---|
| `gemini` | `vertex`, Cloud TTS | `gemini-3.1-flash-tts-preview` | Achernar | What the server's expressive order reads every language with today |
| `v4` | ElevenLabs | `eleven_v4` | Sarah | Under test; Sarah as in round 0 (Acervo's own chooser would pick Bella, the first in the list) |
| `v3` | ElevenLabs | `eleven_v3` | Sarah | Under test, with Acervo's current form only |

Gemini was asked three times per item, because its slips are rare (the owner hears about one in
30). Take 1 is rated; all three are transcribed.

## The set (`set.json`)

43 items drawn with a fixed seed from a read-only pull of the owner's vocabulary.

| Group | Items | Text | Gemini is sent | Eleven v4 is sent | Eleven v3 is sent |
|---|---|---|---|---|---|
| feeling | 9 es-AR, 3 en-GB, 3 ru | Real examples with their stored `emotion`. The Russian ones are the stored Russian translations of English examples, with that example's emotion | `acervo_pronounce_style` | the current tag, `emotion; accent from Argentina` | the same |
| story | 4 es-AR | Passages the server cut, with the direction each was recorded under. No English story had been read with directions, so all four are Spanish | `acervo_pronounce_story` | the current tag, the direction plus the accent | not recorded (credits) |
| accent | 7 lengths × es-AR, es-ES | 1, 2, 3, 5, 8, 12 and 16 words, chosen for «ll», «y», «z», «ce», «ci» | `acervo_pronounce_accent` | four variants, below | not recorded (credits) |
| words | 6 es-AR, 2 en-GB, 2 ru | Headwords; the Russian are glosses of English words | `acervo_pronounce_accent` (Russian: nothing) | nothing, as today | nothing |

The accent variants on Eleven v4:

| Variant | Tag |
|---|---|
| `current` | `accent from Argentina` / `accent from Spain`: Acervo's form with the feeling left out (Acervo sends nothing today) |
| `calm` | `calm and natural; accent from …`: a candidate fix that always gives a feeling |
| `named` | `Argentine Spanish accent` / `Castilian Spanish accent` |
| `none` | no tag: the control. ElevenLabs takes no region, so it is one request for both varieties and is recorded once, under es-AR |

**ElevenLabs credits.** 8,968 were left in the month, after round 0 spent 1,032. The whole plan came
to about 11,700 characters. So the 22-word accent text was dropped, and v3 was given feelings and
words only. The run spent 8,485 and left 483 (`run.py bill` prints the arithmetic).

## Routes and allowances found on the way (`results/probe.json`)

- **Cloud TTS on Vertex has no 3.8 voices.** `gemini-3.8-flash-tts` and `gemini-3.8-flash-lite-tts`
  answer "The model … is not supported". 3.1 Flash preview, 2.5 Flash and 2.5 Pro TTS answer.
- **The `google-key` key does not reach the Gemini API.** It is restricted to Cloud TTS and Vision,
  and Google blocks it there ("Requests to this API generativelanguage.googleapis.com … are
  blocked").
- **The free Gemini API key allows 10 speech requests a day per model.** This is Google's own 429
  on 3.8 Flash-Lite TTS: "limit: 10 requests per day on Free Tier". So it cannot carry a vocabulary.

## Whisper so far (before the owner's ear)

`transcribe.py`: Whisper large-v3-turbo, told each item's language. This is a cross-check, not a
verdict; round 0's transcriber missed an instruction read aloud.

| Take | Takes | Said twice | Instruction read aloud | Other words |
|---|---|---|---|---|
| gemini (all three takes) | 129 | 0 | 0 | 0 |
| v4 (feeling, story, words) | 29 | 0 | 0 | 0 |
| v4 accent `current` | 14 | **2** | 0 | 0 |
| v4 accent `calm` | 14 | 0 | 0 | 0 |
| v4 accent `named` | 14 | 0 | 0 | 0 |
| v4 accent `none` | 7 | 0 | 0 | 0 |
| v3 (feeling, words) | 25 | 0 | **1** | 1 |

- **The bare accent tag doubles short texts on v4, as in round 0.** "Decepcionar. Decepcionar." and
  "Hacer gracia. Hacer gracia." are the 1- and 2-word items, es-AR. With a feeling in front
  (`calm`), or the variety named (`named`), Whisper heard no doubling at any length.
- **v3 read a tag aloud** on an English sentence (`f12`): "revealing someone's true intentions,
  accent from United Kingdom. His polite manner was …". v4 read no tag aloud in 29 takes with one.
- **Gemini said exactly its text in all 129 takes.** The 1-in-30 slip did not show here.

Takes longer than 1.6× Gemini's for the same item: none. The duration check adds nothing to what
Whisper heard.

Still open, for the ear: whether the feeling carries, whether the accent carries, and anything
Whisper smoothed over.

## Commands

```bash
# Read-only pull of the vocabulary and the voice settings, then the set (out/graph.json is ignored)
.venv/bin/python experiments/expressive-voice/run.py set
.venv/bin/python experiments/expressive-voice/run.py probe          # routes; --cap-calls N for the free cap
.venv/bin/python experiments/expressive-voice/run.py bill           # ElevenLabs characters; spends nothing
.venv/bin/python experiments/expressive-voice/run.py record         # resumable, nine minutes a pass

# Whisper in an environment of its own
uv venv experiments/expressive-voice/.venv --python 3.12
uv pip install --python experiments/expressive-voice/.venv/bin/python mlx-whisper jiwer
experiments/expressive-voice/.venv/bin/python experiments/expressive-voice/transcribe.py

.venv/bin/python experiments/expressive-voice/run.py blind          # loudness-matched letters, out/key.json
.venv/bin/python experiments/expressive-voice/review.py --host "$(tailscale ip -4)" --port 8767
.venv/bin/python experiments/expressive-voice/run.py report         # after listening
```

The page shows one item at a time: the text, what was asked, and its takes as letters. Each take is
rated **Right** (wrong / a slip / right), **Feeling** where one was asked, and **Accent** where one
was named. Each take also has flags for *read aloud*, *said twice* and *other words*, and each item
gets a **Best** pick. Every tap is saved to `out/labels.json`. `report` unblinds the labels into
`results/report.md` and `summary.json`, and copies the labels and the key into `results/`.

# Does ElevenLabs read with feeling and accent correctly?

**Status:** recorded and transcribed on 7 Nov 2026 ([`experiments/expressive-voice/`](../../experiments/expressive-voice/README.md)).
The owner's blind listening on the tablet is still to come.

## Why

The expressive voice reads examples and stories with a direction. Gemini voices on Vertex
(Cloud TTS) have done this for about a month, over roughly a hundred real calls, and they are the
reference here. ElevenLabs (v4 and v3, 10,000 credits a month on the free plan) was added on 7 Nov
2026 and is the voice under test: how it has to be sent a direction is not yet known. Gemini's own
known defect is different and rare: it sometimes says a phrase other than the one it was given,
about one take in 30. That is a task of its own, a Whisper check and a retry.

## Round 0: the owner's first listening, 7 Nov 2026

Eight takes in the same voice (Sarah): seven from Eleven v4 and one from v3. The texts were
"picar", "la calle amarilla", and "¿En serio? No me digas que ya terminaste todo el trabajo."

| Take | What was sent | Heard |
|---|---|---|
| 1 | "picar", no direction | Good, even, no emotion |
| 2 | "picar" under Gemini's accent sentence (136 characters) | The word, then the instruction read aloud, then the word again; neutral |
| 3 | The sentence under Gemini's feeling sentence (194 characters) | The instruction read aloud, then the sentence, with the instruction's feeling |
| 4 | The sentence under `[surprised, amused, Argentine accent]` | No instruction heard, with the feeling |
| 5 | As 4, on Eleven v3 | No instruction, with the feeling; more serious and louder |
| 6 | "picar" under `[accent from Argentina]` | Said twice, no emotion |
| 7 | The sentence under `[surprised and amused; accent from Argentina]` | As 4, and liked best |
| 8 | "la calle amarilla" under `[accent from Argentina]` | A very good Argentine accent ("ll"), but said twice, in two intonations; no emotion |

What is built from it:
- ElevenLabs is sent a short tag instead of the long direction: the feeling, plus the accent where
  one was chosen, in take 7's form (`pronunciation/speak.Direction`).
- An accent with no feeling sends nothing, because on a short text it doubled the text.

## Round 1: a fixed set, recorded and transcribed on 7 Nov 2026

43 items from the owner's vocabulary, in Spanish, English and Russian:

- 15 examples with their stored feelings;
- 4 story passages with their directions;
- 10 words;
- 7 Spanish texts of graded length (1 to 16 words), each in both Argentine and Castilian Spanish.

They were read by Gemini 3.1 Flash TTS preview on Vertex (the server's expressive voice, Achernar)
and by Eleven v4 and v3 (Sarah), sent the way Acervo sends them. Eleven v4 was also sent the accent
alone four ways. Whisper listened back to all 232 takes. The method, set and numbers are in the
experiment's README.

What Whisper heard, before the ear:
- **The bare accent tag still doubles short texts on v4.** `accent from Argentina` doubled the 1-
  and 2-word texts (2 of 14). `calm and natural; accent from …` and `Argentine Spanish accent`
  doubled nothing at any length (0 of 14 each).
- **v3 read a tag aloud once**: an English sentence's whole tag, accent included. v4 read none
  aloud in 29 tagged takes.
- **Gemini said exactly its text in 129 of 129 takes.**

Found on the way:
- Cloud TTS has no 3.8 voices; Vertex reaches 3.1 Flash preview, 2.5 Flash and 2.5 Pro TTS.
- The free Gemini API key allows **10 speech calls a day** per model, per Google's own refusal. That
  is too few to read a vocabulary.

## What is left

1. **The owner's listening.** Run `review.py` and open the page on the tablet
   (`experiments/expressive-voice/README.md`, Commands). Each take is rated for the words, the
   feeling and the accent, with flags for an instruction read aloud and a text said twice. Then run
   `run.py report`.
2. **Decide from it:**
   - whether ElevenLabs carries the feeling and the accent well enough to stay in the expressive
     order, and v4 or v3;
   - whether an accent alone should be sent as `calm and natural; accent from …` or as the named
     variety rather than as nothing. Which form, if either, is for the ear: Whisper only says
     neither doubled.
3. Fold the decision into `pronunciation/speak.Direction`, `docs/providers.md` and the pronunciation
   doc, and retire this plan.

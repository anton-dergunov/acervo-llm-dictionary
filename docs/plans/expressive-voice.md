# Which free voice reads with feeling first

**Status:** designed, not run. Both voices are built: the Gemini API's and ElevenLabs'
([`../providers.md`](../providers.md)). What is left is to listen to them.

## Why

The expressive voice reads examples and stories with a direction. At no cost there are two
candidates, and the guide puts the Gemini API first only because it is the cheaper of the two:

- **Gemini API TTS** (3.8 Flash and 3.8 Flash-Lite): free at three requests a minute per model and a
  small daily cap, with voices made for an accent (Argentine, Mexican and Castilian Spanish among
  them). It reads a direction as instructions, in a field of its own.
- **ElevenLabs v4 and v3**: 10,000 credits a month, one per character, the direction included. Its
  free voices are general ones whose accent is their own.

Which one *sounds* better has not been heard. The order should follow the ear.

## What is already known

**Round 0: the owner's first listening, 7 Nov 2026.** Eight takes from Eleven v4 (one from v3) in
the same voice (Sarah). The words were "picar", "la calle amarilla", and "¿En serio? No me digas
que ya terminaste todo el trabajo."

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

What follows, and is built:
- A long direction is read aloud, so ElevenLabs is sent a short tag: the feeling, and the accent
  where one was chosen, in take 7's form (`pronunciation/speak.Direction`).
- The accent tag works, as take 8 shows, but alone on a short text it doubled it, a word (take 6)
  and a three-word phrase (take 8) alike. So an accent with no feeling sends nothing for now.
- A transcriber listening back (Gemini Flash-Lite) heard neither the spoken instructions nor the
  accent. Whether a voice reads instructions or carries an accent is judged by ear.

**Also measured on 6 Nov 2026:**
- ElevenLabs bills the tag character for character. A month of credits buys about 100 sentences with
  a feeling, or 20 story passages.
- The Gemini API guesses the language from the words, and gets a single word wrong without "Say
  this in Spanish." at the head of the direction. The adapter always sends it.

## The experiment

1. **A fixed set**, recorded once through each candidate: 10 words, 15 example sentences with an
   emotion each, an accent alone on 5 sentences and 5 short phrases (es-ES and es-AR), and 4 story
   passages with their directions. It is drawn from the owner's own vocabulary.
2. **Through each of four pairs**: Gemini 3.8 Flash TTS and 3.8 Flash-Lite TTS, Eleven v4 and v3,
   each with the voice Acervo would choose for the accent.
3. **Within the free allowances.** ElevenLabs: under 4,000 characters per model, so both fit in one
   month. Gemini: three a minute, so the recording script paces itself and resumes where it
   stopped.
4. **Rated blind on the tablet**, with the apparatus from `experiments/pronunciation-encoding/` and
   a scoring page and labels file of its own, opened through the server. The questions: is it right
   (words, language, accent), and does it carry the feeling, each on a short scale.
5. **Results** go in `experiments/expressive-voice/`: the set, the replies, the labels and a short
   report.

## What it decides

- The order of the expressive voice in the guide's zero-cost set, and whether ElevenLabs is worth an
  account at all.
- Whether an accent alone is safe on a whole sentence, or how long a text has to be before it stops
  being said twice (takes 6 and 8 were one and three words).
- Whether Flash-Lite TTS is good enough to take the free allowance's load ahead of Flash.

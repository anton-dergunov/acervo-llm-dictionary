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

## What is already known (measured on 6 Nov 2026)

- ElevenLabs bills the direction tag character for character. Acervo's direction sentences, written
  for Gemini, are 136–194 characters, so the adapter sends ElevenLabs the feeling alone as a short
  tag, and nothing for an accent alone (`pronunciation/speak.Direction`).
- An accent tag on ElevenLabs changed no accent a transcriber could hear, and made a short text be
  said twice ("picar, picar"). A feeling tag was heard ("surprised").
- A month of ElevenLabs credits buys about 100 sentences with a feeling, or 20 story passages.
- The Gemini API guesses the language from the words, and a single word is guessed wrong without
  "Say this in Spanish." at the head of the direction, which the adapter always sends.

## The experiment

1. **A fixed set**, recorded once through each candidate: 10 words, 15 example sentences with an
   emotion each, 5 sentences with an accent alone (es-ES and es-AR), and 4 story passages with their
   directions. It is drawn from the owner's own vocabulary.
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
- Whether ElevenLabs should be sent an accent in any form, given that the tag did nothing.
- Whether Flash-Lite TTS is good enough to take the free allowance's load ahead of Flash.

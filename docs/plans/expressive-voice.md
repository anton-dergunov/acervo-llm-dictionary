# Which settings for ElevenLabs?

**Status:** round 1 settled the model and the feeling tag (7 Nov 2026); round 2's pairs are recorded
and waiting for the owner's ear ([`experiments/expressive-voice/`](../../experiments/expressive-voice/README.md)).

## Why

ElevenLabs was added on 7 Nov 2026 so that Acervo works with whatever voice provider people have, and
had never read anything for real. Gemini, with about 200 real calls, stays the default. The question is
only how ElevenLabs should be used so that it works as well as it can: which model, and what it is sent
for a feeling and an accent. Every credit is a character of the tag as well as of the words.

## Settled by round 1

- **Eleven v4 is the one model "Add the usual models" adds.** It carried a feeling on every example and
  read no tag aloud in 61 tagged takes; v3 lost the feeling on 14 of 15 and read its tag aloud once.
- **A feeling is sent as the short tag**, never the sentence Gemini is sent, which round 0 heard read
  aloud.
- **An accent alone is sent as nothing.** The bare `accent from Argentina` said 1- and 2-word texts
  twice (4 of 4 short texts across rounds 0 and 1), and no form of the accent was heard to carry it
  better than no tag.
- **The voice reads in its own accent.** On every Argentine text with «ll» or «y» before a vowel, the
  sound that is heard, Eleven v4 was "not it", with `feeling; accent from Argentina` or nothing.

## What is left

1. **The owner's listening to the pairs.** `pairs.py serve` (the experiment's README, Commands), on the
   tablet: 32 pairs, each one text read under two accents — "which one sounds Argentine?" (or
   British). Then `pairs.py report`.
2. **Decide the accent part of the tag** by the rule in the README: if a form is picked in nearly all
   its pairs and Gemini's pairs show the contrast is audible, keep that form in the tag (built from CLDR
   names, never a hand table); otherwise ElevenLabs is sent the feeling alone.
3. Fold it into `pronunciation/speak.Direction`, `docs/providers.md` (including when ElevenLabs does
   not follow the accent) and `docs/features/pronunciation.md`, and delete this plan.

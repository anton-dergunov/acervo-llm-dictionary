# Known issues

Small defects with a known shape, each fixed on its own. A section says what goes wrong, why when it
is known, and the fix. A fixed issue is deleted from here; a design change it needed goes into the
feature's document.

## §1 · The expressive order offers voices that cannot take a direction

**What goes wrong.** `audioExpressive` is meant to be the voices that take a direction, and nothing
holds it to that. A pair that declares `style: none` can sit anywhere in the order, first included;
when it answers, the direction is dropped and the clip is recorded as though no emotion had been
asked for. Nothing fails and nothing is logged — the only trace is an empty `emotion` on the stored
row. It happened on the owner's deployment: an order saved from Settings ▸ Providers put
`gemini-free` first, and every expressive clip after that lost its direction. Stories exposed it,
spending a model call per passage to place directions that were then thrown away; examples and loops
had been degrading quietly all along.

**Why.** The route, not the model. `gemini-free` and `vertex` reach Gemini TTS through LiteLLM, whose
Vertex text-to-speech transformation has no field for an instruction, so the direction is dropped
before the request is built. `google-tts` reaches the same models through `models/google_tts.py`,
which puts it in `input.prompt`. `style: none` on those rows is honest.

**The fix.**

- Retire the `gemini-free` audio capability from the catalogue (its text capability stays): a speech
  row that cannot do what the expressive order exists for, on about ten free requests a day.
  **Open:** whether `vertex`'s audio row goes with it — it is the same case.
- The expressive order lists only pairs that declare `style: instruction`; Settings ▸ Providers offers
  no other pair there and says why. The shipped `defaultChains.audioExpressive` breaks the rule itself
  by ending in `google-tts/wavenet`; that entry goes.
- A saved order is a preference and is not refused or rewritten. When no expressive pair can be
  reached, the caller falls back to `audioPlain` and records without a direction, with a log line
  saying so.
- `services/story_audio.py` already applies this rule for stories alone. Once the general fix lands,
  delete that guard rather than keep a second implementation.

Not worth doing now: a direct adapter to the AI Studio audio API so the free tier could carry a
direction — new provider work for about ten requests a day.

## §2 · LexiBeat's default seed does not survive JSON

Given no seed, the generator uses `secrets.randbits(64)`, which cannot round-trip through JSON into a
browser. 2^53 does everything 2^64 does, the seed being a replay token rather than a key. Acervo is
unaffected, since it mints the seed itself. **Fixed in the LexiBeat repository**, at its next release,
and re-pinned here.

## §3 · The phone's now-playing bar cannot be dismissed

Once a loop has played, the bar at the foot of the list stays: it has play/pause and a tap target that
opens Loops, and no way to say *done with that*. It wants a close control that stops playback and
forgets the loop as the current one — not delete it. Where the player lives on the desktop is a design
question, [`loops-and-stories.md`](loops-and-stories.md) §4.

## §4 · Folding a photo sentence into a held word loses the photo

A sentence tapped in a photographed page and folded into a word already held goes through the article
conversation, which carries text, so the attestation arrives without the photo that a new word's
attestation keeps ([`../features/photo-capture.md`](../features/photo-capture.md)).

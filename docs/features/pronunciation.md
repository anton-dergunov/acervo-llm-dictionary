# Pronunciation · hearing a word, and any sentence about it

Every spoken field can be heard: a headword, a sense's definition, an example, an attestation, and any
stretch of text the owner selects. The server records it, the device keeps it, and it plays offline.
The package is `src/acervo/pronunciation/`, which stands alone like `images/`; the binding layer is
`services/pronunciations.py`; the measurements are
[`experiments/pronunciation-encoding/`](../../experiments/pronunciation-encoding/README.md). Loops and
stories use the same voices through their own routes ([`loops.md`](loops.md),
[`stories.md`](stories.md)).

---

## A recording is a record

`pronunciations` is a replicated collection. A row names the file under `ACERVO_MEDIA_PATH`, the words
that were spoken, the language, the emotion the voice was actually given, and the provider, model and
**voice** that spoke it — so a voice changed later is detectable on the recordings made before it
rather than silently mixed in with them.

- **Its id is derived from what it reads**: `pronunciation_id(targetKind, targetId)`, implemented in
  `pronunciation/ids.py` and `web/src/ids.ts` and pinned against shared vectors. So a spoken field has
  at most one recording, and recording it again rewrites that row.
- **Stale is a comparison, not a flag.** A recording is current while its `text` equals what the record
  now says. Edit the sentence and the next press records the new words; nothing marks anything.
- **The file name carries a digest of the bytes**, so a new recording is a new reference and a device
  holding the old one misses rather than playing what was just replaced.
- **A selection is the one thing spoken and never stored**, on the server or the device: it names no
  record, so there is nothing to make stale. Every rendered block carries a `lang` attribute, which is
  how `selectionSpeech.ts` splits a selection into runs of one language each.

**Recordings are replicated, where pictures are not**, and that is measured rather than tidy: a spoken
headword is a couple of kilobytes against a picture's hundred, so a vocabulary's recordings cost about
what its text does. The bytes are kept in `mediaStore.ts`'s own store, switched on per device in
Settings ▸ Pronunciation (on by default), and `fill()` brings down what the replica names after each
sync — which is what makes a word recorded on another device play on a plane.

**Recording is a write**: online, loud when it fails, never queued. Recording in advance is a step of
the server's `enrich` job, switched on per kind in Settings (headwords, definitions, examples); a press
on a field that has no recording yet records it there and then.

## What a recording is stored as

**The provider is asked for the uncompressed master, and Acervo compresses it** to Ogg Opus in
`pronunciation/encode.py`, at libsndfile compression 0.8 — about 55–68 kbps on real clips: a headword
is ~5.7 KB and an expressive sentence ~34 KB, against 234 KB for its master.

This was settled blind. Cloud Text-to-Speech answers `MP3` at 32 kbps for a Gemini voice, and in a
blind test of one performance encoded five ways every file the listener flagged was that MP3; Opus at
~30 kbps was indistinguishable from uncompressed except for one "not sure", and smaller than the MP3.
Asking the API for `OGG_OPUS` would be simpler and worse: it answers at 28–35 kbps with no way to ask
for more, while the master costs nothing extra (the API meters characters, never bytes) and leaves the
bitrate ours. `M4A` is not an option: the API returns MP3 bytes under that name, or refuses it.

Two rules come with it. **An answer that arrived already compressed is stored as it arrived** — a
second lossy generation adds artifacts to save kilobytes. **A missing encoder refuses the recording**
rather than quietly keeping a master twelve times the size. A selection is compressed too, since it is
downloaded before it can be heard.

## Two orders, four uses

Two voice orders are chosen in Settings ▸ Providers, named for their capability:

- **`audioPlain`** — a clear, even voice. The default is Cloud TTS WaveNet, then Standard.
- **`audioExpressive`** — a voice that takes a direction. The default is Gemini voices on Cloud TTS,
  which take the emotion in a field of their own, so it is never read aloud. **Only such voices read
  it** — see below.

Which one reads each **use** is a separate choice, `pronunciation_settings.delivery`: *words and
definitions* (default plain), *example sentences*, *loops* and *stories* (default directed).
**Choosing the directed order is asking for emotion** — there is no separate emotion switch that could
leave the expensive voice reading every sentence flatly.

The split is not "plain versus expressive" for its own sake. **A headword's recording is a
reference**: one per word, offline, correct, and read by one voice held stable per language, so a
deviation is audible. **An example's recording is a reading**, where prosody carries meaning and a
voice that takes a direction earns its cost.

Both orders draw from a provider's one `audio` kind, because any voice can read either. What a voice
can do is said **per model** — whether it takes a `direction`, and the `languages` it speaks where the
owner says — since one Google endpoint serves per-locale WaveNet voices that take no direction and
Gemini voices that speak anything and do; the voices themselves come from the provider's own list
([`../architecture/models.md`](../architecture/models.md), "Providers and families"). A direction is a
short English phrase the compose prompt writes, sent only to a model that takes one, and recorded on
the row only when it was actually sent.

## Accent, and which voice reads first

**The accent is the vocabulary's variety** (`vocabularies.region`: `AR`, `GB`, `419`), set in
Settings ▸ Vocabularies, because it is a fact about what is learned rather than about a voice — the
writers follow it too ([`standing-rules.md`](standing-rules.md), "The reader"), and the clip search may
([`../plans/languages/accents.md`](../plans/languages/accents.md)).
The voices are its first reader: everything spoken in that vocabulary is asked for in its locale,
`es-AR`, and a vocabulary with no accent is asked for in the bare language exactly as before.
**Which accents a language is offered is CLDR's answer, not a list in the code**
(`locales.accents`): every region where CLDR says the language is official, de facto official or
official in part of the country, with at least 200,000 speakers, most speakers first — Mexico,
Argentina, Spain, Colombia, the US… for Spanish — then a wider region two of them share (`419`,
Latin America). Where a language is only widely learned (English in Germany) is no accent of its
own and is left out. The speaker counts are CLDR's too, through `langcodes`, since Babel does not
carry them. The server sends the list with each language in `GET /languages`, so a language's
varieties are offered before its vocabulary exists, and the form adds any region a voice is declared
for.

**Providers handle accent in two ways, and both come from what the provider says, never code.** A
voice made for one locale carries it (Google lists `es-ES-Wavenet-F` under `es-ES`) and has that
locale's accent. A voice that speaks any has no locale of its own, and when its model takes a
direction it is *told* the accent — "as a native speaker from Argentina", in the same field as the
emotion, so it is never read aloud — and sent the nearest locale the model accepts: the ones typed on
it, else the ones the provider lists voices under. Gemini voices refuse `es-AR`, so for Argentina
they are sent `es-US`. Which locales are near is CLDR's answer, read through Babel in
`models/locales.py`: `es-AR`, `es-MX` and `es-US` share `es-419`, so for Argentina a US Spanish voice
outranks a Castilian one, which is still offered. `Provider.voice_options` ranks a model's voices for a locale — made for it, told it, near, the
language's main locale, another — and that ranking is the only place accent is matched. A test holds
the code that chooses a voice to naming no provider, model or voice, so a provider added later is
ranked the same way by filling in the same fields. A voice made for a locale is told nothing extra:
its accent is the one it was made for. The accent alone is not an emotion, so a clip records an
emotion only when the emotion was what was sent.

**Which voice reads each language is the owner's choice, per order** — one clear voice and one
expressive voice per language, in Settings ▸ Pronunciation. Choosing a voice sets two things:
the voice that pair says the language in (`pronunciation_settings.voices`, per pair and language),
and that the pair **reads first** for that language (`first_voices`, `{order: {language: [provider,
model]}}`). The rest of the order are its backups, in Providers order; a backup that offers the same
voice name says it too (Kore on one Gemini model, then the next), and otherwise says its best voice
for the accent unless the owner chose one for it. `pronunciations.readers` applies the choice for
every use — words, examples, selections, loops, stories — and `settings_view` returns the resulting
walk per order and language (`readers`) so the page draws it rather than restating the rule. Each
choice is held to the provider, and a voice a model does not offer is dropped rather than sent;
removing a provider or one of its voices removes the choices that named it. The
voice is recorded on every clip. One limit follows from the storage: a pair in both orders says a
language in one voice, so choosing a Gemini voice as both the clear and the expressive voice keeps the
later choice for both.

A loop's guide lines are chosen the same way (`guide_voices`, `guide_first_voices`), in the order that
reads loops. **Changing the accent or the voice records nothing again**: a clip is stale only when its
words change, and "Record again" replaces one at a time.

## Hearing a voice before choosing it

`POST /pronunciations/preview` reads a sample in exactly the voice pressed and the vocabulary's
accent. The pair is pinned, so nothing falls through to a backup and what is heard is what was
pressed. Nothing is stored; the call log has a `pronounce-preview` line, and a refusal keeps the
provider's sentence there like any other.

**The page chooses the sample, from the replica** (`voiceSample` in `selectors.ts`): the newest
example written in the language, with its emotion for the expressive order, or failing that the
newest word. A loop's guide says the translations, so its voice reads the newest example translated
*into* its language — which exists even when no vocabulary is kept in that language — and falls back
the same way. With nothing in the language at all the page says to add a word and asks nothing. The
page keeps a played sample for the session **under the words it says** as well as the voice, so a new
example is heard the next time rather than an old one replayed, with nothing to invalidate.

## The take route, for loops

`POST /pronunciations/take` is how the loop generator gets a voice, and it is not the utterance route.
It answers the **master**, losslessly as FLAC — the one place Acervo keeps audio uncompressed —
because a take is about to be stretched, pitched and mixed into a track that is itself encoded, so the
only lossy generation in a loop is the final MP3. Masters are kept in a content-addressed store beside
the database (`pronunciation/takes.py`) where the digest is the filename, and **`take` is in the key**:
two takes of one line can carry byte-identical directions, and without the index the cache would serve
one recording three times. **A take recorded without its direction is looked for only once no
directed voice can read the line**, so a day without one does not leave those lines flat in every
later loop. The design is [`loops.md`](loops.md) §2.4–§2.5.

## The interface

A recording plays with no request when the device holds it. **A bad recording is replaced from the
toast**: after a stored recording plays, the message offers Record again — the moment you know a
recording is bad is the moment you have just heard it, and a control under every sentence would be a
page of buttons. Players stop each other: the pronunciation player, a loop's and a story's each
register their pause, and each silences the others before it plays.

## Why nothing speaks on the device

- **Nothing needs to synthesise there.** Every sentence that can be spoken arrived through a write, and
  writes are online, so the server records it the moment it exists and the recording reaches the device
  on the same pull as the record. A neural voice in the browser would cost 60–180 MB per language to
  close a window that is already closed.
- **The device's own voice is not a fallback.** `speechSynthesis` cannot be captured, so it can never
  fill a cache; and a device with no voice for the language reads Spanish in an English voice, often
  without the page being able to tell. A pronunciation reference that may teach the wrong sounds is
  worse than none.
- **Batching words into one call buys nothing.** Speech is metered by characters or by audio duration,
  and neither shrinks when ten words share a request; only the request count does, and splitting the
  result back into words needs alignment. A request-metered tier is answered by choosing a
  character-metered provider.

Not built, deliberately: speech-to-text, pronunciation assessment (recording the owner and scoring it
is a product of its own), a second media store, and voices running on the device. Voices running on the
NAS and other providers are [`../plans/provider-management.md`](../plans/provider-management.md).

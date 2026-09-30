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

**Which voice reads each language is the owner's choice**, per model and language, in Settings ▸
Pronunciation (`pronunciation_settings.voices`), held to what the catalogue declares: each choice is checked against the
catalogue, and a voice a model does not offer for the language is dropped rather than sent. That is what holds a
headword to one stable voice per language, and the voice is recorded on every clip.

Both orders draw from the catalogue's one `audio` kind, because any voice can read either. Audio
capabilities are declared **per model** (`capabilities.audio.models`: style, languages, locales,
voices), since one Google endpoint serves per-language WaveNet voices that take no direction and
Gemini voices that speak anything and do. A direction is a short English phrase the compose prompt
writes, sent only to a model whose row declares `style: instruction`, and recorded on the row only
when it was actually sent.

**The expressive order is read only by voices that take a direction** (`pronunciations.readers`, the
one place this is decided, for examples, loops and stories alike). A voice that cannot take one used
to sit anywhere in the order and, when it answered, record the clip as though no emotion had been
asked for — nothing failed and nothing was logged, and on one deployment every expressive clip lost
its direction that way. Now:

- Settings ▸ Providers offers only `instruction` voices for the expressive order, and says why; the
  catalogue refuses an expressive default that names any other.
- A saved order is a preference and is kept as saved. The walk skips a voice that cannot take a
  direction; the pane does not draw it, so the next change the owner makes saves the order without it.
- **When no directed voice can answer** — none left in the order, or every one refusing for a quota,
  a busy provider or an unusable answer — the plain order reads, without the direction, and the call
  log carries `result=undirected` with the reason. A rejected credential is raised, not routed around.
- Gemini speech is reached only through Cloud TTS. Through LiteLLM the Gemini API and Vertex have no
  field for an instruction, so neither the free tier nor Vertex offers speech.

A pair that does not speak the language is left out of the walk; a chain
where none does answers `no_voice_for_language`, naming what to fix. `pronunciation/targets.py` decides
the *use* and never the order, because that package may not read settings.

## The take route, for loops

`POST /pronunciations/take` is how the loop generator gets a voice, and it is not the utterance route.
It answers the **master**, losslessly as FLAC — the one place Acervo keeps audio uncompressed —
because a take is about to be stretched, pitched and mixed into a track that is itself encoded, so the
only lossy generation in a loop is the final MP3. Masters are kept in a content-addressed store beside
the database (`pronunciation/takes.py`) where the digest is the filename, and **`take` is in the key**:
two takes of one line can carry byte-identical directions, and without the index the cache would serve
one recording three times. The design is [`loops.md`](loops.md) §2.4–§2.5.

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
NAS, other providers and human recordings are
[`../plans/provider-management.md`](../plans/provider-management.md).

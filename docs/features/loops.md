# Loops · how Acervo uses LexiBeat

**Built.** [`lexibeat`](https://github.com/anton-dergunov/lexibeat) is the owner's loop generator, a
separate project that Acervo runs as one pinned service. This is how the two meet.

A word's article can say what a word means, show a picture of it, play a native speaker using it, and
read every field aloud. What none of that does is get a word *stuck in your head*. A loop does: in
its plainest format, the word and one translation, each spoken three times on a bar grid over a
procedurally synthesised bed, with a silence in the middle to recall the answer in; in a richer one, a
presenter between the words with an example, a remark, a quick quiz, or a short story told a line at
a time. Twelve words from whatever you are looking at — or the ones you marked — become a
four-minute track you can put on in the kitchen. It plays with the screen locked, shows every line as
it arrives, and is made by a server job you can walk away from.

LexiBeat keeps everything that makes a loop sound like anything — the formats, the number of takes,
how each take differs, the bed, the ducking, what a writer is asked for. Acervo lends it words, one
direction per word, a voice, and a writing model. It is the **second** companion service, after the spoken-usage corpus
([`spoken-clips.md`](spoken-clips.md)); where it departs from that template it says why.

---

## §1 · What the other repository gives

LexiBeat's own `README.md`, `design.md`, `music-generation.md` and `service.md` are the
detail; in short:

- **A procedural music engine, not a model.** Four stems — `pad`, `bass`, `drums`, `lead` —
  synthesised with numpy and `scipy.signal` from sampled instruments, against a known beat grid. No
  GPU, no network, no model call, and byte-identical from a seed. **This is why a loop can be built on
  the NAS at all.**
- **A deterministic bed description.** A family plus a seed replays exactly, down to each sample's
  digest, and `bedFingerprint` proves it did.
- **Programme formats.** A format — `classic`, `alternating`, `echo`, `review`, `radio-lesson`,
  `story` — is a recipe of sections and steps with a few switches (its `docs/programme-format.md`).
  `classic` is word, gap, answer, twice more, then a rest. Every line starts on a downbeat; a written
  line takes the bars it needs.
- **A writer seam.** A format that speaks written lines — examples, remarks, a story, an intro — asks
  an injected writer once per render, and parses the reply itself. The host owns the model call.
- **Three takes per line, each delivered differently** — and **how** depends on what the voice can
  do, which §2.6 is about.
- **A mix that ducks** each stem from the speech envelope, speech at −16 LUFS and music at −26.
- **Two views of what was said**: `items`, one row per word with where its block starts and ends and
  when each side is first heard, and `cues`, every line in the order heard, each with its `group` — the
  lines a player shows together — its role, language, text and span. That is the player's data.
- **A sample bundle of about 3.1 GB**, content-addressed with a SHA-256 per asset, fetched once onto
  the server (§2.15).
- **One injection seam that matters**: the speech backend is supplied per render by the host, which
  is how Acervo lends a voice (§2.3).

---

## §2 · The decisions

### 1 · Two repositories, one version pin

The template is [`spoken-clips.md`](spoken-clips.md) §2.1: `deploy/acervo/lexibeat/pin.json` names one version, one tag
and a digest per artifact, and `scripts/fetch_lexibeat.sh` turns that into gitignored
`vendor/lexibeat/`. Digests come from the release's own `SHA256SUMS`. A locally built wheel that
matches is left alone, which is what makes "try it before tagging" work; anything the pin does not
name is pruned, because the image installs `vendor/lexibeat/*.whl` and two wheels of one package fail
the build.

There is no npm half. LexiBeat ships no player component; the loop player is Acervo's.

### 2 · A service beside Acervo, holding no provider key

A compose service with no published port, reached at `http://lexibeat:8000/api/v1`, in an image that
is **Acervo's** — the package does not self-daemonize, so process, volumes and URL are the host's.

Unlike the retrieval image it carries no `acervo.models` and **no provider credential at all**,
because of §2.3. It is therefore the one companion service absent from `test_deployment.py`'s "every
service that calls a model is given the same credentials" tuple, and a test asserts that absence
deliberately so a later reader cannot mistake it for an oversight.

Its healthcheck asserts **liveness**, and not that the sample bundle is present: a fresh deployment
has no bundle and still serves. Readiness gating would fail the install of a working service, which
is the lesson the corpus service taught first.

**It serves without the bundle; it cannot render without it.** The first version assumed a
pack-less render falls back to the synthesised `electronic` palette, so the interface would warn
rather than refuse. It does not: fifteen of the sixteen bed
families name instruments loaded from the catalogue, so the render dies partway through on a missing
sample and how far it gets depends on which voices the seed happens to draw. `POST /loops` therefore
refuses with `loops_no_samples` before writing a row. The healthcheck is unchanged and still
deliberately does not gate on it — *installing* a server without its samples is fine, and the
refusal belongs on the one route that needs them.

### 3 · LexiBeat synthesises; Acervo lends it a voice

**The service receives words, not audio.** `{items: [{source, target, emotion}], format, switches,
script, family, seed}`. It decides how many takes, how each differs, where the downbeats fall, what a
writer is asked for, how the bed resolves and how the mix ducks.

An earlier draft had Acervo record the lines and post the audio. It was wrong three ways, and the
reasons are worth keeping:

- **It split the arrangement across two repositories.** Changing three repetitions to four would have
  meant changing both, which is the opposite of letting that project be iterated on alone.
- **It contradicted that project's own interface**, which takes a word and decides delivery itself. A
  second, audio-shaped entry point would have been a second way in, permanently.
- **It missed that the three takes are three recordings.** Acervo holds at most one clip per spoken
  field by construction, so "the word's audio" is exactly the thing it cannot supply.

**So the seam is a provider, injected.** And this is where it differs from the translation seam, which
is handed `acervo.models` in-process: everything a speech call needs here is database state a
companion container cannot read. `services/pronunciations.py:_speak()` already resolves the owner's
chain through `chain_for`, the owner's per-model voice through `preferences.voice`, the hedge, and the
`no_voice_for_language` refusal that names what to fix. Copying the provider package across would
mean passing the chain *and* the voice map in the request and reimplementing the voice lookup and
that refusal on the far side — duplication, and a third copy of every credential on the NAS.

So the injected `Backend` is implemented in `deploy/acervo/lexibeat/serve.py` as a call **home**, to
the route in §2.4. One rate limiter, one cooldown, one call log, one place the owner chooses. LexiBeat
sees only a Protocol, so if the balance ever changes, moving to in-process LiteLLM edits `serve.py`
and nothing else.

**The protocol** `serve.py` satisfies:

```python
class Backend(Protocol):
    name: str
    sample_rate: int
    capabilities: BackendCapabilities   # emotion, rate, voice, languages
    load_seconds: float
    model_id: str

    def synth(self, request: SpeechRequest) -> SynthesisResult: ...
```

`SpeechRequest` carries `text`, a `Language(code, name)`, a `Delivery(take, direction, prosody,
pace, quotes)`, `target_seconds`, `seed` and a `role` — `native` for a line in the language being
learned, `guide` for one in the listener's own. Four things about it are load-bearing here.

**Dispatch reads `capabilities`, never a name.** `Speaker` used to look its post-processing flags up
by the backend's name string, so an injected backend raised `KeyError` before it spoke a word. Acervo's backend declares
`BackendCapabilities("instruction", "instruction", "preset", languages=())`, and the empty tuple
means "any language" — the owner's chain decides what it can speak, not a table in the other
repository.

**`take` is on the request**, which is what makes §2.5's cache key implementable at all: the index
would otherwise have to be re-derived from the prosody, and two takes can carry identical prosody at
low strength.

**`role` goes home with every take**, and the take route reads it: a guide line — a translation, a
remark, an announcement — is said by the owner's guide voice where one is chosen (§2.4). The backend
declares `mixes_languages` exactly when the owner's loop order takes a direction, because only then
does a line's director note reach the voice. That matters for a guide line that quotes the language
being learned — "Anhelar is poetic; for everyday wanting, say *tener ganas de*": LexiBeat names the
quoted spans in the note ("Say “Anhelar” and “tener ganas de” in Spanish, with a native Spanish
pronunciation, and everything else in English"), which is what made an English voice say them right,
and a format that needs it requires `multilingual_voice`. The sentence travels inside `direction`, so
the take route needed no field for it.

**`backend_factory` is the seam**, not a module-level object: `create_service(backend_factory=…)`
takes a callable given a `RenderContext(operation_id, request, credentials)` and returns a `Backend`.
`credentials` is the render-scoped token of §2.3, handed to that callable and to nothing else — it
appears in no operation body, no result and no log line, and `lexibeat.voice.register_secret` adds it
to that package's own provider-text redactor.

**No credential sits in that container.** `POST /loops` carries a short-lived token signed with
`ACERVO_JWT_SECRET`, scoped to one render and audienced to the take route; `serve.py` builds the
backend for that request around it, which works because `render_lesson_speech` takes its backend per
render. Nothing is stored, nothing outlives the render, and there is no login flow — narrower than
`acervo-worker`'s owner password, which is a one-shot container rather than a service.

Minting that token is `src/acervo/tokens.py`, a leaf that knows JWT and a secret and nothing else: a
render is a job, `work/` may not import `api/`, and minting used to live in `api/auth.py`, which now
re-exports it. There is no startup dependency in either direction: render requests arrive *from* the
server, so the server is up whenever a call comes home.

### 4 · `POST /pronunciations/take`, and why it is not `utterance()`

`{text, language, direction | null, take, role}` → the **uncompressed master**, plus
`X-Acervo-Provider`, `X-Acervo-Model`, `X-Acervo-Voice` and `X-Acervo-Direction: sent | dropped`.

- **Not `utterance()`**, which exists for a selection and compresses to Opus because the bytes are
  downloaded before they can be heard. A take is about to be time-stretched, pitch-shifted and mixed;
  it wants the master, so that the only lossy generation in a loop is the final MP3.
- **Not a plain-or-directed choice made by the caller.** The route reads the owner's *loop* delivery
  setting (§2.7) and reports whether the direction was honoured. **A dropped direction is a useful
  answer, not a failure**: LexiBeat falls back to its own pitch and speed variation, so a deployment
  with no instruction-following voice still gets loops — with three distinguishable takes and no
  emotion — and that requirement is met by the contract rather than by a branch on either side.
- **Not one voice for every line.** `role: guide` reads the owner's *guide voice* for that model and
  language (`pronunciation_settings.guide_voices`, chosen in Settings ▸ Loops), merged over the usual
  voices; unset, the usual voice says it. A role that is neither is refused.
- **Not uncached.** §2.5.

**The field is called `direction` on the wire**, not `emotion`. `emotion` is the *record's* field
name — what §2.8 writes onto a lexeme, and what an example already carries — and it stays that.
LexiBeat has no notion of an emotion: it receives a short English phrase saying how a line should be
said, appends the take's prosody words to it, and puts the result in the director note. Naming it
for what it is on the far side keeps the two vocabularies from being confused for one, and the
mapping is one line in `src/acervo/loops/`.

**What the generator sends as a direction is its whole director note** for that repetition, pace and
pitch included, and the take route frames it with `prompts/acervo_pronounce_take.md` rather than the
example template. It has to be a prompt of its own: the example template inserts a bare adjective
after "sounding" and then tells the voice to keep a natural pace, which cancels the one clause that
makes a word's three takes differ. **Nothing in that prompt may say how many repetitions there are**:
how often a line is said, and how each saying differs, is the generator's.

**The chosen delivery travels with the render** as `speech.delivery`, because the generator declares
what its injected voice can do when it builds it and cannot find that out on its own. That is what
makes the clear voice worth what it says: one recording a line, varied locally by pitch and speed,
rather than three identical calls — and what makes a dropped direction reachable at all. The route
reports `X-Acervo-Direction: sent`, `dropped` or `none`.

### 5 · The take cache, and why `take` is in the key

Behind the route sits a content-addressed store of **FLAC masters**, keyed by a digest of
`(text, language, direction, take, provider, model, voice)` — so a guide voice's take and the usual
voice's are two recordings, never one. The digest *is* the filename, so there is
no table and no schema. FLAC because it is lossless and about half of WAV: this is the one place in
Acervo where FLAC is the right answer, and the delivery format is not it.

It pays for itself twice. A word that appears in two loops is recorded once. And a render that dies
half way — a rate limit, a restart, a deploy — resumes against the takes that already exist, which is
what makes §2.10's retry cheap rather than a second bill.

**`take` is in the key deliberately, and this is the subtle part.** `delivery_instruction` quantises a
continuous `Prosody` into a grid of adjectives, so two takes of the same word can produce
*byte-identical* instructions — at a low prosody strength the takes converge by design. Without the take
index the cache would hand back one recording for both, and the repetition would sound **more**
mechanical, not less. A provider that ignores seeds hides this without a cache, since two identical
prompts happen to give two different readings; a cache turns that accident into a guarantee in the wrong
direction.

**A stored pronunciation is deliberately not read through.** It is tempting: a plain headword take has
the same text, language, model and voice as the clip the article already holds. But that clip is Opus
at about 51 kbps, compressed for a phone, and stretching and mixing it would put a second lossy
generation in front of the master. It would save one call per word in the plain case and none in the
directed case. `experiments/pronunciation-encoding/` exists to have settled exactly this trade, and
this is it being settled.

### 6 · Three takes, and what actually makes them differ

This deserves its own section because the mechanism is not uniform, and the integration sits on top
of the part that is weakest.

| The voice | How the three takes differ |
|---|---|
| Instruction-following (Gemini, Vertex, OpenAI) | **Only through words.** `delivery_instruction` turns speed and pitch into adjectives inside the prompt; `exaggeration_bias` and `gain_db` are discarded. |
| Post-processing (Cloudflare, Kokoro's pitch) | **Locally**, by time-stretch and pitch-shift on the returned audio. |
| Chatterbox | **Model-side**, by `exaggeration` alone; it has no speed or pitch control. |

Acervo's loops land in the first row, and three things follow.

**One:** a directed take is a separate model call per repetition — three per line, so roughly 72 for a
twelve-word loop. A plain take is one call per line, varied locally: roughly 24. That is what the
setting in §2.7 actually buys, and the document says so rather than leaving it to be discovered.

**Two:** the quantisation had dead zones, and `emphatic` fell in one — at full strength, takes 0 and
2 of an emphatic word resolved to speed 1.030/+0.30 st and 1.051/+0.70 st and *both* said "slightly
briskly, with a slightly brighter, higher pitch". **Each axis was widened from three bands to
five**, and a test asserts the three takes of a line are pairwise distinct. Note that the emotion
table that pushed both takes past one threshold is itself gone: a direction is free text now, so the
multiplier that caused the collision no longer exists either. §2.5's key remains the belt, because at
a *low* prosody strength the takes converge by design — that is what "vary less" means.

**Three:** `gain_db` had never done anything, in any backend: it was applied and then divided
straight back out by the peak-normalise eleven lines later, so the −0.8/+0.6 dB column of
`Prosody.TABLE` was decoration. **It was reordered** — normalise to the reference peak, then apply
the gain, then hold the result under the ceiling — and a test asserts two takes differing only in
`gain_db` have measurably different peaks.

### 7 · Two orders named for what they are; three uses pick one

Labelling the voice chains by use — *words and definitions*, *example sentences* — with a switch deciding
only whether a direction is *sent* would mean switching emotion off still spends the expensive voice on
every sentence, and each new use would want a chain of its own.

So there are two orders named for their capability — *a clear, even voice* and *a voice that takes a
direction* — and each use picks one: words and examples in Settings ▸ Pronunciation, loops in Settings ▸
Loops, stories in Settings ▸ Stories. **Choosing the directed order is asking for emotion**, which is why
the old `expressive` switch was deleted rather than left beside the new control: one mechanism
where there were two, and the cheap voice finally reachable for examples as well as loops.

No third chain. Any voice is a legitimate answer to either question, which is exactly why the catalogue
has one `audio` kind and `defaultChains` has two orders over it.

### 8 · `primaryGloss` and `emotion`, written by the compose prompt

`shortGloss` is right for the list and wrong for a loop: *casa* → `house, home` cannot be spoken on a
beat. What a loop needs is one term, the most common reading, roughly as long as the source — and a
direction for how the word is said.

```yaml
headword: asco
shortGloss: disgust, revulsion       # unchanged, the list line
primaryGloss: disgust                # the one term spoken
emotion: repulsed, recoiling slightly
```

**Named for what they are, not for what consumes them.** A future flashcard, quiz or second kind of
lesson can use both without either name lying. And `emotion` is the same field an example carries, at
a different level: same meaning, same short-English-direction format, same rules in the prompt, read
by the same `acervo_pronounce_style.md` machinery.

**On the lexeme, not the sense**, because a loop drills a word and must choose exactly one meaning.
Asking per sense produces three answers where one is wanted, and moves the choice away from the writer
that has just read every sense.

**`primaryGloss` follows `glossLangs[0]`**, exactly as `shortGloss` and a sense `domain` do, and there
is deliberately no setting for it. A vocabulary's gloss languages are already ordered most preferred
first, so reordering them *is* the control. A setting over a single stored string could only end up
naming a language the stored text is not in.

**The wording that decides them is measured.** `emotion` is written for most words rather than kept for
the vivid ones: the compose prompt asks the writer to picture the single most ordinary situation the word
comes up in, and treats a description of flatness — "neutral", "matter-of-fact" — as `null` rather than a
sentence; `primaryGloss` is long enough for a multi-word headword (`encender la computadora` is not
`turn`). That wording measured 88.6–100% `emotion` coverage on ordinary words with 0% false positives on
null controls, holdout included, and was confirmed on the real vocabulary
([`experiments/primary-gloss-emotion-tuning/`](../../experiments/primary-gloss-emotion-tuning/README.md)).

**And this is measured before it is trusted.** The risk is not that the fields are wrong but that a
larger prompt thins the *rest* of the article — fewer senses, shorter notes, a `primaryGloss` that is
just `shortGloss` again. `experiments/compose-lesson-line/` runs the amended prompt against the model
set and a fixed word list and compares everything except the new fields against what the current
prompt produces. If it degrades, the answer is **not** to carve two fields into their own call — that
is too small a piece to justify a second prompt. It is to split `acervo_compose.md` into comparable
parts, considered whole, as its own task. The write-up records which way it went.

**Measured on 18 September 2026, and it does not degrade:**
[`experiments/compose-lesson-line/`](../../experiments/compose-lesson-line/README.md).
315 calls over 20 words, four languages, three (provider, model) pairs and three repeats.
**All ten substance metrics move less than their own run-to-run variance** — senses +0.04 against a
noise floor of 0.13, note characters −15.7 against 58.4 — gloss completeness is 100% in both arms,
and the only unparseable reply in the run came from the *shorter* prompt. `primaryGloss` was a single
term in all 158 usable replies and never once copied a multi-meaning `shortGloss`.

The subjective half could not resolve anything at this size: agreement with a Pro-model judge over
all 155 pairs was κ = −0.097, at chance, and the experiment's README explains why its same-prompt
controls are weak evidence either way. Pairwise "which is better" is the wrong instrument for
differences this small, and the next prompt experiment should not repeat it.

So **the fields ship as worded and `acervo_compose.md` is not split.** Two bars were missed and
neither bears on it: note characters at 89.4% on a metric whose difference is a quarter of its noise,
and the gloss-language rule, failed only by `llama-3.3-70b` and only on a rule that predates these
fields. Article quality itself is untouched by this run and has its own register,
[`../plans/article-quality.md`](../plans/article-quality.md) — both arms wrote `/ˈaska/` for `el asco`, which is simply
wrong, and a comparison of two arms is blind to a defect they share.

### 9 · A loop is three collections, and its state is derived

`loops` — `language`, `format`, `switches`, `fallbackFrom`, `styleId`, `seed`, `engineVersion`,
`bedFingerprint`, `audioRef`, `audioMime`, `durationSeconds`, `position`. `loopItems` — `loopId`,
`lexemeId`, `position`, `sourceText`, `targetText`, `emotion`, `startSeconds`,
`sourceRevealSeconds`, `targetRevealSeconds`, `endSeconds`. `loopCues` — `loopId`, `position`,
`group`, `kind`, `section`, `loopItemId`, `side`, `role`, `language`, `text`, `take`, `startSeconds`,
`endSeconds`.

- **No status column.** An empty `audioRef` is *not rendered yet*; the job says the rest. `ImagePrompt`
  already lives by this — four facts say all of it, and a fifth would be a thing to keep in step.
- **No BedSpec blob.** Style, seed and engine version replay the bed byte-identically, and
  `bedFingerprint` is what proves it did.
- **`format` is the generator's catalogue id and `switches` the listener's choices** — a small map of
  on/off and named values, sent with every render of the loop. Neither is opaque: Acervo checks both
  against the generator's schema when a loop is asked for. `fallbackFrom` names the format asked for
  when the render lacked something it requires and made its fallback; `format` then says what the
  track is.
- **The text is denormalised on purpose**, in items and lines alike. They record what was *said*, so
  editing the word afterwards must not make the player caption a recording that no longer matches.
  Identical reasoning to `pronunciations.text`.
- **Every line is stored, as the render reported it.** A radio lesson says an intro, examples,
  remarks and a quiz that no per-word shape could describe, so the render's cue list becomes
  `loopCues` row for row, with its `item` index mapped to the `loopItemId` it names and its `group`
  kept as the generator numbered it. The lines are written by the render and only by it: new music
  tombstones a loop's lines and writes the new ones. A word's reveal on `loopItems` is null for a side
  its block never says.
- **What the writer wrote is kept, and not replicated.** `loop_scripts` — one row per loop, the
  generator's own shape, read by nothing but the next render — is server-only, exempt from the
  replicated rules like `jobs`. It exists so new music says the same lines (§2.18).
- **No title.** `selectors.ts` derives one from the source words that fit, as `effectiveShortGloss`
  derives a gloss.
- **`position` orders them**, sparse and renumbered on reorder, with no uniqueness constraint — that
  is the data rule, and ordering is respected rather than enforced.

`pronunciations` gains nothing: no new target kinds, no new derived ids. Reordering and deleting are
ordinary graph writes, so online-only and loud when they fail, like every other write.


### 10 · A render is an operation, followed like `corpus.update`

Seventy-odd model calls plus a bed and a mix is minutes, not seconds. So `POST /loops` answers an
operation id, and the job polls it, marking the step `waiting` and raising `Requeue` exactly as
`work/corpus.py` does. That buys progress the owner can watch, cancellation between polls, and no
multi-minute blocking call inside the runner.

The CPU work happens in the companion container, which is what keeps the runner's rule
([`jobs.md`](../architecture/jobs.md)) — *"anything heavy is out of scope for the runner"* — true rather
than merely restated. The job holds the **`audio` lane**, because that is the allowance a render
spends: every line is a call home to the take route. Nothing is held in memory between its two
steps — `loop.render` writes the operation id down and `loop.store` reads it back — so a retried step
re-enters with everything it needs. `loops_busy` and `loops_unreachable` are transient and rest like
the model codes; `loops_failed` is not, a finished-and-refused render being a fact about that
request.

A rate limit surfaces as one of the three transient codes and rests as usual; the take cache is why
the restart is cheap.

**The service's routes**, all written out because the allow-list rule of
[`spoken-clips.md`](spoken-clips.md) §2.9 applies to them as it does to the corpus:

| Route | Answers |
|---|---|
| `GET /api/v1/health` | `{status, api_version, engine_version, production_bundle}` — liveness only |
| `GET /api/v1/schema` | formats, profiles, families, energy, rhythm, palette, limits, audio |
| `POST /api/v1/loops` | `202` with an operation |
| `GET /api/v1/operations/{id}` | the operation, with `result` once it completes |
| `DELETE /api/v1/operations/{id}` | cancels between utterances |
| `GET /api/v1/loops/{id}/audio` | the finished track, `audio/mpeg` |

The operation is `{operation_id, status, successful, error, progress: {fraction, message},
created_at, updated_at, result}`, with `status` one of `queued | running | completed | failed |
cancelled`. That is **deliberately the corpus's vocabulary** — the one
`src/acervo/clips/corpus.py`'s `Operation` already models and `src/acervo/work/corpus.py` already
follows, down to `finished` being "not queued and not running". So `loops/client.py` is a second
instance of a pattern rather than a second pattern, and `work/loop.py` is `work/corpus.py` with a
different noun.

The completed `result` carries `audio_url`, `audio_mime`, `bitrate_kbps`, `duration_seconds`,
`format`, `fallback_from`, `style_id`, `seed`, `engine_version`, `profile_version`,
`bed_fingerprint`, `total_bars`, `bpm`, `items`, `cues` and `script` — which is exactly §2.9's three
collections and the kept script, and nothing else. A cue naming a word the loop does not have is
refused rather than stored. **The resolved
BedSpec is deliberately not in it**, on that service's side as well as this one, so there is nothing
for a host to be tempted into storing.

### 11 · MP3, written there and stored untouched

LexiBeat writes the finished track as **MP3 at 128 kbps** and Acervo stores those bytes exactly as
they arrive, into `ACERVO_MEDIA_PATH`, with the row through `merge_graph` — file first, row second, as
`services/pronunciations.py` does, because nobody else holds both.

No re-encoding on the NAS, and no change to `encode.py`, which already states the rule this follows:
*"a provider that already returned MP3 has its bytes stored exactly as they arrived; re-encoding a
lossy stream into another lossy codec adds a second generation of artifacts."* A loop arrives
compressed, so it is stored as it arrived.

MP3 rather than Opus because the content is speech over a generated bed where 128 kbps is inaudible
from the master, and because the phone decodes it in hardware, seeks in it trivially, and will cache
it as a plain file later. Verified rather than assumed: that project's `soundfile` 0.14.0 over
libsndfile 1.2.2 writes MP3 and Ogg Opus with no new dependency and no ffmpeg.

**And the bitrate is measured rather than declared.** libsndfile exposes quality as a 0–1
`compression_level`, not a bitrate, so "128 kbps" is a claim that has to be checked: in
`bitrate_mode="CONSTANT"` the level maps onto LAME's own bitrate ladder, and `0.65` is the rung that
is 128. Measured on a 124.5-second loop, 1,993,664 bytes — **128.1 kbps, constant**. A test in that
repository re-measures it on every run, so the pair cannot drift apart.

### 12 · Words come from what you are looking at

The interface samples N lexeme ids from the scope on screen — this language, this topic, or everything
— as a pure selector over the replica, and posts the list. The server never re-derives scope, and the
route takes ids rather than a query.

That is what made the next step cheap: **choosing words by hand is the same route with a different
list** — the device's word selection ([`word-selection.md`](word-selection.md)), built with no
server change.

**The style and format catalogues are LexiBeat's**, read from its `schema` route and never copied here
— the rule [`spoken-clips.md`](spoken-clips.md) §2.10 settled for channels. The dialog offers *Surprise me* or a family
the service advertises, and each format with its own label, sentence and switches, so a new family or
a new format appears here with no change at all. `GET /api/v1/schema` is that route: it reports
`formats` (each with its `switches`, what it `requires` and its `fallback`), `families`, `energy`,
`rhythm`, `palette`, the request `limits` and the `audio` format, plus `production_bundle`. Acervo's
`GET /loops/schema` passes the formats through and adds the two facts only it knows —
`writerAvailable`, whether the owner's text chain can answer, and `mixesLanguages`, whether the loop
order takes a direction — so the dialog can say what a format needs before it is chosen (§2.19).

### 13 · The way in, and no second bar over an article

Loops have their own surface, and the way in is **one component in two skins** (`MadeBar.tsx`, shared
with stories and the map), so what the two say cannot disagree:

- **On a phone, a bar at the foot of the window, split in three — Loops, Stories and the Map** — where
  these belong on a device held in one hand. `.app` grows that third grid row **only when no article,
  external entry or Add view is open**.
- **On a desktop, a button at the foot of the topic rail, beside Stories**, and a chip in the top bar
  **only while something is sounding**. The top bar already holds search, scope, Add, sync, settings and
  the language menu, and a way in to every learning method would crowd it.

**No second bar over an article.** The article pane is 780 px of column already carrying the view
segments, the delete control, the progress strip and `AskDock`, and a second dock there is prohibited.
It cannot collide by accident: `AskDock` renders only when an article is open and the bar only when one
is not. The bar has no **+**: each surface carries its own Make button in its own header, and a bar whose
job is to be a way in should not also be a way to start something.

A loop keeps playing while you read a word — the audio element is not the surface — and the now-playing
row is on the bar when you come back. **There is no mini-player over an article.**

The word selection's bar is the one deliberate exception to the no-second-bar rule, and only on a wide
window while the ask dock rests. The topic rail stays wherever there is room for it and goes only on a phone,
because a surface you leave running is one you come back from, and the way back has to be somewhere;
one back arrow, search, ⌘K and Escape all leave it.

**The player is an ordinary music player with its controls at the foot** — of the three layouts drawn
in the prototype, the only one where the thing you reach for never moves. They are the footer of a
column that owns its height, not a sticky element inside a scroller, which still drifts at the ends
of a scroll. **Every line is drawn, as cards**: one per `group` of `loopCues`, so a word and its
translation are one card, an example and its meaning another, a remark or a line of a story a card
of its own, and a line said three times is one row. A quiet divider names the quiz or the review
where the loop enters it; each line carries its language. **Within a card, nothing after its first
line is drawn before it has been said** — a translation not before it is spoken, a quiz's answer not
before it is given, an example's meaning not before it is heard; a fixed-width bar stands in its
place, and each line keeps a fixed least height so nothing moves when it arrives. `loopCards`,
`loopMomentAt` and `loopLineShown` derive all of it from the clock, which is what makes dragging
backwards put an answer away again. **Which line is sounding is marked in colour and nothing else** —
no weight, size, offset or motion — because this is the one surface meant to be left running and
glanced at. Previous and Next step card by card; the seek line keeps one tick per word. A long line
is set smaller on the card being played, fixed per line so it never changes under the eye.

### 14 · The track plays from memory

The media route is behind bearer auth, so its URL cannot go in an `<audio src>` — the same reason a
picture is fetched as a blob.

The constraint is the better design. A whole track in memory means **nothing touches the network during
playback**, which is what a locked screen and a lift need. `mediaStore.ts` keeps loops as a kind of their own,
so a device can keep or forget loops without touching a picture or a pronunciation; `loops.ts` sets
MediaSession metadata — the format's name among it — and action handlers, and the display is
driven from `loopCues`.

One rule: **players stop each other.** Each registers its pause with
`pronunciation.registerPlayer` and calls `silencePlayers` before it plays — a story's is the third.
Two audio elements racing for one output is a bug with no good failure mode. The iOS gesture
priming in `pronunciation.ts` applies here too.

A signed media URL that would let the browser stream by range is **not** built: a new credential shape
for a file better held whole.

### 15 · The sample bundle is fetched on the server, and size is the whole reason

About 3.1 GB cannot ride a tarball streamed over ssh, and binary data does not enter this repository.
A compiled dictionary rides the release archive because it is small enough to; this is not.

So `pin.json` names the bundle, its parts and its digest, and **`./deploy.sh --install-samples`** is
the one way it arrives: it fetches and verifies the bundle into the directory the running service
mounts. The obvious hand-typed `docker compose run --rm lexibeat lexibeat-bundle fetch …` omits the
deployment's env file, so compose falls back to a named volume and three gigabytes unpack, verify and
report success into a store nothing serves from — a failure that looks exactly like a success.

**The bundle is pinned by its root as well as its digest, and must be complete.** The entrypoint
points the engine at `bundle/<root>` and nowhere else, so a volume still holding a superseded bundle
reads as *no* bundle and is refused by name; `production_bundle` is true only when every file the
manifest names is on disk, because a render drops a bed whose sample is missing rather than failing.
Both matter because the manifest's **expansion policy** switches on the strings, contrabasses and
Wave 3 leads: the 1.96 GB library an earlier pin named served perfectly and rendered audibly plainer
music, with nothing anywhere saying so.

It is the dictionaries arrangement — the owner's own data, moved between the owner's own machines,
populated once and rarely again — and it is never deleted by `--reset-data`.

**Licensing is not a reason for any of this**, and an earlier draft of this document said it was. The
bundle's one attribution-bearing source is CC-BY 3.0, which permits redistribution and commercial use;
the only condition is credit, and it already travels inside the bundle's own `licenses/` directory and
the other repository's `NOTICE.md`. The rest is CC0. Publishing a *generated loop* would mean crediting
that one source; running the tool imposes nothing at all.

### 16 · One word that may not appear

The obvious English word for what a loop does to you is a **commercial product name for a product that
does the same thing**, and is prohibited in both repositories — in code, comments, identifiers,
documents and directory names. The one occurrence Acervo had, a `models/redact.py` docstring, now
says `lexibeat`. The other repository checks it in CI, building the pattern from two halves at
runtime so the check is not itself the one occurrence.

This is also why the artifact is a **loop** rather than a lesson: "lesson" will be overloaded the day a
second kind of lesson exists, and a loop is a thing that repeats, which is both accurate and free.

### 17 · What is deliberately not built

- **No Chatterbox, no local model, no GPU** in this integration. A local voice is its own question
  ([`../plans/provider-management.md`](../plans/provider-management.md)), and the injected-provider seam
  means trying one later changes nothing here: it would be one more row in the owner's chain.
- **No second provider layer, credential set, rate limiter or cooldown store** — the whole point of
  §2.3.
- **No compatibility path and no backfill.** A word without a `primaryGloss` is not eligible for a
  loop; nothing adapts it, nothing fills it in later, and the database is rebuilt.
- **No loop in an export bundle.** A loop is a rendering of words the bundle already carries, from a
  seed the record names — reproducible, and megabytes of it is not what a text archive is for. Study
  state is left out for the same kind of reason.

---

### 18 · New music, kept beds, and deletion

**New music is the same job with a different input, never a write to the row.**
`POST /loops/{id}/music` takes a family, a seed, both (a kept favourite) or neither (the same style
afresh), refuses with `loop_busy` while a render for that loop is open, and queues `loop` with
`{family, seed}` as its input. The row's `styleId` and `seed` go on describing the track it holds
until the store step replaces both with the new track, so a render that fails changes nothing.
**New music keeps the lines**: the render sends back the script the last one returned
(`loop_scripts`), which LexiBeat reads exactly as a fresh reply and calls no writer for. So a radio
lesson's examples and remarks survive a change of music word for word, every take is found in the
cache, and new music costs render time and no provider spend. The dialog offers the
generator's own styles without `auto`, which is the absence of a choice and is called *Surprise me*.

**A kept bed is a `beds` record**, not a flag on the loop: `styleId` and `seed` replay it for any
words, and `sourceLoopId` outlives the loop it came from. The star in the player writes or tombstones
it as an ordinary client write; the make dialog offers kept beds first and sends one as family *and*
seed, since a seed read with `auto` may land on another family.

**A loop is deleted by a route**, `DELETE /loops/{id}`, because the track is megabytes that nothing
else would ever remove and the row and the file must be written by the same party. The file goes
after the rows land, never before.

**Acervo mints the seed.** Left alone the generator uses `secrets.randbits(64)`, and a 64-bit integer
does not survive JSON into a browser, where a number is a double — the first render that got as far
as storing was thrown away over one. The generator echoes back what it is given, so the stored seed
is provably the one that made the bed, and Try again reproduces it. The stored bound is JavaScript's
safe integer, which is the real constraint.

### 19 · Formats: chosen in the dialog, written by the owner's text model

**The make dialog offers the formats as cards**, the generator's label in bold and its sentence
beneath, and the chosen one's switches under it — an on/off switch as a checkbox row, a choice as a
row of segments ("Times each word is said: 2 3 4"). It opens on the format last made on this device,
with that format's switches as they were last set: a device fact, like the player's switches. The
request carries `format` and `switches`, and the server checks both against the schema and refuses a
format or a switch the generator does not offer by name.

**A format that needs what this server lacks says so before it is chosen.** A radio lesson requires a
writer and a loop voice that can mix languages, and falls back to the classic drill without either;
its card says "Falls back to Classic drill here" and names what to set up and where. A story requires
a writer and has no fallback, so without one its card is disabled and says why. A loop that fell back
anyway — the state changed between asking and rendering — says so beside the player.

**The writer calls home, like the voice.** LexiBeat's injected `Writer` is `AcervoWriter` in
`serve.py`, posting `{prompt, purpose}` to `POST /loops/write`, which walks the owner's **text** chain
— the stories' chain, every call in the call log — and answers `{text, provider, model}`. The render
token's audience is widened from the take route to both loop routes and nothing else. The prompt, the
parser and what a good line is are LexiBeat's; the model, its credentials and its retries are
Acervo's. **The reply is plain text**, never JSON mode or a schema ([`models.md`](../architecture/models.md)
on constrained decoding): LexiBeat's parser checks every part it relies on and refuses the reply
naming the first fault, and a refusal's sentence survives every hand-off. One writer call per render,
and none for new music.

---

## §3 · Measured, and what the deployment taught

**A render, rehearsed against a real Acervo and the real bundle**, three words over the directed
order (`X-Acervo-Direction: sent`):

| | |
|---|---|
| Render | 65.5 s for 79.1 s of audio |
| Per utterance | 3.6 s — 18 takes, all recorded |
| Per word | 21.8 s |
| Track | 1.3 MB, 128 kbps, stereo |

So a twelve-word loop is about 72 takes, roughly **4½ minutes**, and the job polls in seconds rather
than the corpus job's twenty. `acervo_worker.py loop render` makes one by hand and prints these
timings; the poll and timeout in `work/loop.py` are set from them rather than from feel.

What the first deployment found, each a fault worth not repeating:

- **`pedalboard` needs `libatomic1`**, which slim-bookworm does not ship. Without it LexiBeat fell back
  to librosa, which the slim runtime deliberately lacks, and the render died nine utterances in
  naming the wrong dependency. The image installs it, and LexiBeat now names the real failure.
- **A failure's sentence was thrown away three times** — by `services/loops.refusal`, by the runner's
  rollup, and by `ProgressStrip` — and between them they turned "No samples cached for 'salamander'"
  into "the loop could not be made". Each keeps the message now, and `work/journal.py` logs it
  ([`../plans/observability.md`](../plans/observability.md) is the wider question).
- **The Loops surface could not be left.** Every obvious exit was a dead end; §2.13's rules are the
  fix.
- **The Music selector was a no-op** until the family was validated, carried on the job and passed to
  the render — so Try again asks for the same music too.
- **A render says what it is doing** in its own words — "Synthesizing speech", "Rendering the music
  bed", "Mixing" — rather than a fixed "Being made…" written on this side.

---

## §4 · How it is checked

The wire shape is checked offline against responses recorded from the real service, as the corpus
client is, plus a gated live contract test; a copy of that service's OpenAPI document is not
committed here, for the reason [`spoken-clips.md`](spoken-clips.md) §4 gives.

By hand, and worth doing after any change to this path:

- **On the NAS, end to end** — make a twelve-word loop, watch its steps, then make a second sharing
  several words and confirm from the call log that the shared takes cost nothing.
- **A plain-voice loop** — set loop delivery to the clear voice and confirm the render succeeds,
  `X-Acervo-Direction: dropped` comes back, and the three takes still differ audibly. A radio lesson
  asked for then is made as a classic drill, and the player says so.
- **A radio lesson and a story, end to end** — every line is on screen as it is said, an example's
  meaning and a quiz's answer only once heard; a quoted Spanish word in an English remark is said in
  Spanish; with a guide voice chosen, the guide lines are audibly the other voice.
- **New music keeps the lines** — change a radio lesson's music and confirm the same examples and
  remarks come back, the call log shows no writer call, and the takes are cache hits.
- **On the phone, which is the only test that matters** — the words track the audio; it keeps playing
  with the screen locked, with lock-screen controls; a kept loop plays with no connection; a word's
  play button stops the loop rather than overlapping it.
- **The rules still hold** — reordering or deleting a loop offline fails visibly and changes nothing
  locally; an export bundle contains no loop; a word with no `primaryGloss` is refused by name.

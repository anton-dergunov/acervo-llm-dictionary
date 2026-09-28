# The data model

The vocabulary is a graph of owner-scoped records: `topic → lexeme → sense → example / attestation /
imagePrompt / pronunciation / studyState`, with a lexeme belonging to any number of topics, and
beside it the things made from words — loops and stories. Every record is replicated in full to every
device ([`sync.md`](sync.md)). The canonical client model is `web/src/domain.ts`; the server's is
`src/acervo/domain/`, and the two are kept identical by validation on both sides.

---

## The collections

In merge order — a record's references always point earlier in the list, so a batch applied in this
order always resolves, and tombstones cascade in the reverse order.

| Collection | One row is | Notes |
|---|---|---|
| `vocabularies` | one language the owner studies, and how it is presented | exists before its first word, which is what makes a new language fillable |
| `topics` | an editable grouping, with an icon and an order | data, never a fixed enum |
| `lexemes` | the thing being learned | a word or a phrase: `ponerse malo` is a lexeme with `pos: phrase` |
| `senses` | one meaning, ordered | definition in one language, glosses in several |
| `attestations` | where the owner actually met the word | verbatim, and the one irreplaceable record |
| `examples` | an illustrative sentence under a sense | generated, curated, drawn from an attestation, or a recorded clip |
| `imagePrompts` | one sense's picture and how it came to exist | id derived from the sense |
| `pronunciations` | one spoken field's recording | id derived from what it reads |
| `studyStates` | a word's, or one of its senses', review state in one learning system | written back from Anki |
| `loops`, `loopItems`, `loopCues` | a rendered track, each word in it, and every line it says | hang off no word |
| `stories`, `storyParts`, `storyWords` | an illustrated story, its parts, and the words it was asked to teach | |
| `beds` | a loop's music, kept to be asked for again | outlives the loop it came from |

Loops, stories and beds sit last because they hang off no word; that is also what puts them inside
"Delete all words".

### Fields on every record

`ownerId`, `deleted`, `createdAt`, `editedAt`, `editedBy`, `revision` — snake_case at the storage
boundary. **Deletions are tombstones**, never removals. **`revision` is assigned by the server** and
is the only ordering used to decide whether a record is newer; `editedAt` and `editedBy` are
provenance — when, and from which device — and never a merge key.

---

## The word

### Vocabulary: three languages, not interchangeable

| Field | Is | Why it is separate |
|---|---|---|
| `definitionLang` | the language senses are defined in, usually the target language itself | a definition is short and formulaic, so reading it in the target language is cheap practice |
| `glossLangs` | the languages translated into, most preferred first, never empty | one word can carry an English gloss *and* a Russian one |
| `notesLang` | the language usage notes are written in, defaulting to `glossLangs[0]` | a note is unbounded contrastive prose — the part of an article you skim |

`shortGloss`, `primaryGloss` and a sense's `domain` follow `glossLangs[0]` and deliberately have no
setting of their own: the order of the gloss languages *is* the control. Every prose field in the
compose prompt states which of the three it is written in, because a field whose language is
unstated drifts from request to request.

**No field is ever named `l1` or `l2`.** The shorthand assumes one native language and one being
learned, which is exactly what a multilingual learner breaks: English can be both a target and the
pivot Spanish is glossed in. Every language-bearing field names *which* language, never a role.

### Lexeme

`language` (BCP-47), `headword`, `lemma` (the dictionary form, and the key a corpus or dictionary is
searched on), `reading` (pinyin or another script aid — **required for Chinese**, on a prefix test),
`ipa`, `pos`, `gender`, `register`, `dialect`, `emoji`, `topicIds`, `status`, `notes`,
`clipsSearchedAt`, and three gloss-shaped fields that are not interchangeable:

- **`shortGloss`** — the list line, which may carry several distinct meanings (`house, home`). Null
  unless curated: by default it is derived from the first sense.
- **`primaryGloss`** — the **one** term a loop speaks, because `house, home` cannot be said on a beat.
  A word without one is not eligible for a loop, and nothing fills it in later.
- **`emotion`** — how the word itself sounds when said: the same short English direction an example
  carries, one level up.

**`status`** is `inbox → active → learned → retired`, plus **`suppressed`**: without a way to say *"I
saw this and decided not to learn it"*, the same word arrives through capture forever and a duplicate
check cannot tell a new word from a rejected one.

**`clipsSearchedAt`** answers two questions with one field: null means the corpus was never consulted;
set with no clip means it was, and nothing was good enough. It is written only on a successful
consultation ([`../features/spoken-clips.md`](../features/spoken-clips.md) §2.8).

### Sense

`definition` in `definitionLang`, `glosses` as `[{lang, terms[]}]`, a one-word `domain`, the sense's
own `emoji`, and an `order` — the common meaning first, because sense order is information. **Both the
definition and the glosses are kept, and neither is privileged**: the target-language definition pins
the sense's boundaries and is extra input in the language being learned; the gloss is the *click* of
recognition. `turmoil → суматоха` is where the gloss does the work, and `sobremesa` — with no gloss
worth the name — is where only the definition does.

### Attestation — the table worth fighting for

Where the owner met the word: `text` verbatim, typos included, with an optional `translation`,
`sourceUrl`, `sourceTitle`, `sourceKind` (web · book · conversation · video · lesson · sign · unknown)
and `capturedAt`. It is the only data in the system that is genuinely irreplaceable — a model can
regenerate every gloss and example, but nothing can reconstruct the sentence you were reading when you
met the word.

A photographed one also carries `photoRef` and `photoRegion`, and may then have empty text: a street
sign has no sentence ([`../features/photo-capture.md`](../features/photo-capture.md)).

### Example

`text` and `textLang`, an optional `translation` and `translationLang`, `origin`
(attestation · llm · tatoeba · subtitle · wiktionary · manual), `sourceAttestationId`, `modelId`,
`emotion`, `note`, `imageRef`, `matchedForm`, `matchedTranslationForm`, and — for a recorded clip —
`videoRef`, `videoTitle`, `videoChannel`, `videoStart`, `videoEnd` and `clipRef`.

- **Attestations are not examples.** The verbatim sentence stays an attestation; the cleaned-up example
  drawn from it carries `origin: "attestation"` and names it, so the entry shows the corrected sentence
  and the original is one hop away. Punctuation and capitalisation are repaired; wording is not
  invented.
- **`matchedForm` and `matchedTranslationForm`** hold the surface forms the sentence actually uses —
  `pica` for the lexeme `picar`, `itches` in the translation — and must occur verbatim in the text.
  They exist so emphasis stays a field and the sentence stays a plain string, rather than inline
  markup becoming a second storage format.
- **A clip is an example with `origin: "subtitle"`**, not a table of its own. `videoRef` is what its
  other fields hang on: any of them without it is refused on the way in and hidden on the way out.
- **`emotion`** is how a speaker would sound saying the sentence, as a short direction in English that
  a voice able to take one follows when reading it aloud.

```jsonc
// attestation — verbatim, never rewritten
{ "text": "espero que se mejoren pronto un abrazo a toda la familia",
  "sourceKind": "conversation", "sourceTitle": "WhatsApp — grupo del curso" }

// the example drawn from it — cleaned, translated, pointing back
{ "text": "Espero que se mejoren pronto. Un abrazo a toda la familia.", "textLang": "es",
  "translation": "I hope you get better soon. A hug to the whole family.", "translationLang": "en",
  "origin": "attestation", "sourceAttestationId": "attest000000001",
  "emotion": "warm and tender, a goodbye full of care" }
```

### Image prompt, pronunciation, study state

- **`imagePrompt`** — one sense's picture: the scene brief, `styleId`, `seed`, the example it was built
  from, the model that wrote the brief and the one that drew it, `attempts`, `failureReason` and
  `suppressed`. **Its state is derived, never named**: `imageRef` set is ready, empty with no attempts
  is waiting, empty with a `failureReason` has failed. `suppressed` is a field rather than a tombstone
  because the id is derived from the sense — a tombstoned row would be re-briefed at the same id
  ([`../features/sense-images.md`](../features/sense-images.md)).
- **`pronunciation`** — one spoken field's recording: what it reads (`targetKind`, `targetId`), the
  words actually spoken, the language, the emotion the voice was actually given, the file, and the
  provider, model and **voice**. Stale means the record no longer says those words
  ([`../features/pronunciation.md`](../features/pronunciation.md)).
- **The review history is not a collection.** Every answer Anki recorded is kept in `reviews` on the
  server alone — years of it are hundreds of thousands of rows no device needs whole — append-only
  and keyed by Anki's own review id, so the same review sent twice adds nothing. It is read as
  figures through `GET /stats` ([`../features/anki.md`](../features/anki.md), "The review history").
- **`studyState`** — one row per word, sense and learning system: `system`, an optional `senseId`,
  Anki's `noteId` and `cardIds`, and the scheduler's own reps, lapses, stability, difficulty,
  retrievability and last review. **A row with a sense reports on that meaning's cards; a row without
  reports on the word's own**, hearing it, which no single meaning owns. A list shows a word by its
  least stable row. Keyed by system so a second learning tool never collides with Anki, and removed
  with its sense.

---

## Things made from words

**A loop** is its format and the listener's switches for it, the bed's identity (`styleId`, `seed`,
`engineVersion`, `bedFingerprint`), the track (`audioRef`, `audioMime`, `durationSeconds`) and a
`position`; **its items** record each word it teaches and when its block is heard, and **its lines**
(`loopCues`) every line it says — words, translations, examples, remarks — as the render reported
them, grouped as the player shows them. **A story** is its kind, style, title and the note the owner gave the writer; **its parts**
are a paragraph, its translation, a picture and a recording per passage; **its words** are the words
it was asked to teach and the forms it actually used. **A bed** is a loop's music kept to be asked for
again. The designs are [`../features/loops.md`](../features/loops.md) and
[`../features/stories.md`](../features/stories.md).

Three rules they share:

- **State is derived, never a status column.** A loop with no `audioRef` is not rendered yet; a story
  with no parts was never written; a part with no passages is not recorded. A status would be one more
  fact to keep in step with the ones that already say it.
- **What was said is denormalised on purpose.** A loop item's and a story word's `sourceText` record
  what was spoken or asked for, so editing the word afterwards cannot make a caption describe a
  recording it does not match. Deleting the word leaves these rows alone, pointing at a tombstone.
- **Opaque blobs are not replicated.** A loop's bed is replayed from `styleId`, `seed` and
  `engineVersion` rather than kept as a resolved description. The one blob kept is server-only: what
  the generator's writer wrote for a loop (`loop_scripts`), sent back with new music so the lines
  stay the same, and read by nothing else.

---

## The rules

- **Ids are 15 lowercase alphanumeric characters, minted by clients**, and stored unchanged in the
  server, IndexedDB, every relation and every consumer manifest. Minting on the client keeps id
  allocation out of the write path. **Three ids are derived** rather than random — a namespaced SHA-256
  in base 36, implemented twice and pinned against shared vectors from both sides:
  `image_prompt_id(senseId)`, `clip_example_id(senseId, clipRef)` and
  `pronunciation_id(targetKind, targetId)`. That is what lets a saved document and the server's own
  enrichment work on one sense without coordinating, and what holds a sense to one picture and a field
  to one recording without a uniqueness constraint. Every writer must derive them.
- **A document that names no stored entry may carry ids its producer minted**, so records created
  together can reference each other; one editing a stored entry may not, and an unknown id there is
  refused.
- **Provenance is modelled, never flagged.** A sentence the owner supplied is an attestation; the
  example drawn from it names it; a generated example carries `origin: "llm"` and its `modelId`; a
  recording names the voice that spoke it. There is no "the user wrote this" field. `origin` plus
  `modelId` on every generated row is what makes bulk regeneration safe.
- **Every record is owner-scoped**, and related records must share the owner — an example's
  attestation, or an image prompt's sense, must also belong to the same lexeme. An id already held by
  another owner is refused as `id_conflict`, never overwritten.
- **No uniqueness constraints on replicated collections.** Server-only tables that never replicate —
  `sync_state`, `model_selection`, `jobs`, `loop_scripts` — are exempt.
- **A vocabulary language is a record, not a table in the code.** `languages.ts` supplies only the
  defaults a record falls back on.
- **Any change to a replicated record's shape bumps `LOCAL_SCHEMA_VERSION`** in `repository.ts`, and a
  replica written under another version is wiped and pulled again ([`sync.md`](sync.md)).

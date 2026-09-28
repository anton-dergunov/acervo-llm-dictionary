# Article chat · the article is the thing you argue with

Capture builds an entry. What it cannot do is everything after you read it and find it not quite
right: you want another example, the definition explained further, or the one thing no dictionary
gives you — **how this word differs from the neighbouring one you keep confusing it with.**

> **DECISION: chat lives inside the article, and its output is a proposed revision of that record.**
> The value is entirely in the conditioning: a model handed the canonical record, its shape and the
> owner's related words answers a different class of question than one handed a block of text, and
> can return something structurally valid rather than something you transcribe.

- **A proposed change is shown, never applied.** The model answers in prose and, when the answer
  implies an edit, offers one. You review it on the article itself and save it or not.
- **Approving is an ordinary save**, at the record's current revision, refused if the entry moved
  underneath. A chat-driven edit is indistinguishable downstream from a typed one.
- **The YAML editor stays**, and chat is why: it is the review surface's escape hatch for the case the
  chat gets wrong. A generated store you cannot open and correct directly is one you have to trust
  blindly.
- **Chat is a consumer of the core**: no storage of its own, no article format of its own, and a
  transcript that costs nothing to lose.

What follows is how the model returns an edit, how the edit is shown, where the conversation sits on a
phone, and the four places in the interface that open one.

---

## §1 · What is actually missing

Acervo can build an entry and it can read one. It cannot be argued with. Everything that happens
*after* the entry is on screen and not quite right currently has one route: open the YAML, and be
an editor.

Four situations, all of them ordinary, none of them served:

1. **Explain.** *What is the difference between `el traje` and `el disfraz`? Why is that subjunctive?
   Is this note actually true?* The answer is prose. Nothing changes.
2. **Improve.** *Add a note about how it differs from `el traje`. Give me one more example, in a
   restaurant. This translation is stiff — fix it.* The answer is an edit to one small part of one
   record.
3. **Contribute.** *I heard this on the radio: «…».* That sentence is an **attestation**, and the
   example drawn from it carries `origin: "attestation"`. This is not a variant of (2): the data
   model treats it differently, and so must the chat.
4. **Look up something you do not hold.** A word found through external dictionaries, whose entries
   are — honestly — uneven. The useful question there is *what does this actually mean, and should I
   keep it?* The only action available is the one that already exists: capture it.

The workaround for all four needs no software — copy the article into a chat, ask, paste back —
and it is the wrong shape: the model does not know the schema, so the
answer is prose you re-key by hand; it does not know the rest of the store, so it cannot say *"you
already have `mareo`, and here is the contrast"*; and the round trip is long enough that you stop.

> ### The one-line summary
> **A turn of conversation returns prose, and — only when the turn implies a change — a set of small
> edit operations against the record. The operations are applied to a draft on the device, the draft
> is rendered as an ordinary article with change marks, and approving it is the same
> `saveArticle(parseArticle(text))` call every other write already makes.**

---

## §2 · Prior art, and what is worth taking

| Product | The pattern | What is worth taking |
| --- | --- | --- |
| [Notion — suggested edits](https://www.notion.com/help/suggested-edits) | Edits land in the document itself, underlined and coloured; removals struck through rather than deleted; ✔/✕ per suggestion. | **The document is the diff.** No separate compare view. This is exactly right for an article. |
| [Notion AI — edit with AI](https://www.notion.com/help/guides/notion-ai-for-docs) | Select text → prompt → accept / discard / try again. | Selection as the unit of conditioning. A model told *which part* stays inside it. |
| ChatGPT Canvas / Claude Artifacts | Document on one side, conversation on the other; the model rewrites in place. | The split works on a laptop and collapses badly on a phone — see `§7`. |
| Cursor and the IDE agents | The model returns *targeted edits*, not a rewritten file, and the editor applies and marks them. | The whole of `§4`. This is a solved problem and the solution is structured operations. |
| Google Docs / Gemini "help me refine" | Suggestions arrive as comment-shaped cards anchored to a paragraph. | Anchoring. A suggestion that points at a paragraph is easier to judge than one that floats. |
| Apple Writing Tools | Sheet over the content, content stays visible, results replace in place. | The sheet, and the discipline of a very short result. |
| [Migaku](https://migaku.com/) | AI explanation of a word in context, word-by-word sentence breakdown, from inside the card. | The closest thing in this space, and it stops at explanation: nothing it says can change the card. That gap is the whole opportunity. |
| Readwise Reader — Ghostreader | Prompt presets ("explain like I'm 5", "define in context") beside the text; the result can be saved as a note. | **Presets beat a blank box on a phone**, where typing is the cost. Becomes `followUps` in `§5`. |

Two negative findings matter as much:

- **Nobody in language learning does (2) or (3).** Migaku, LingQ and the Anki AI add-ons all
  generate a card and then leave it alone. An editable, model-assisted personal entry is not a
  feature Acervo would be copying.
- **The chat-beside-the-document layout is a desktop artefact.** Every product that has it also has
  a phone build where it degrades to a full-screen chat that hides the document — which is precisely
  the thing being discussed. `§7` refuses that.

---

## §3 · Three decisions

### §3.1 · How the model returns an edit

| | Whole draft returned | Text patch on the YAML | **Structured operations** |
| --- | --- | --- | --- |
| Wire size | O(article) every turn | small | small |
| Reuses `composeArticle` | yes | no | partly |
| Localised by construction | **no** | yes | **yes** |
| Failure mode | silently drops a field, rephrases an untouched sense | applies in the wrong place with no error signal | names an id that does not exist — **caught** |
| Small model tolerance | poor | poor | good |

The literature is unambiguous and matches what IDE agents converged on: a whole-file rewrite is
capability-dependent and non-deterministically drops or perturbs untouched content, and a
model-authored unified diff is worse — under a tolerant patcher a meaningful fraction of diffs
apply *in the wrong place, silently*. Path-addressed structured operations are validated at the
field level before anything is applied.

The configured default model here is `gemini-3.1-flash-lite`. That settles it on its own.

> ### DECISION
> **A turn returns prose plus, optionally, a list of at most twelve edit operations addressed by
> record id.**
>
> **Because** the operations are checkable before they are applied — every id either exists in the
> document that was sent or the whole proposal is refused — and because "add one example to sense 2"
> is a thing the model can get right, where "reproduce this article with one example added" is a
> thing it can get *almost* right.
>
> **And crucially:** the operations are the *wire format only*. They are applied to produce a new
> draft, and the change marks in `§6` are computed by comparing the two drafts by record id — never
> by reading the operations. If the operation language ever proves to be a bad fit for a future
> model, whole-draft return can replace it without touching the interface at all.

### §3.2 · Tool calling, or one constrained answer

Tool calling would buy a multi-turn loop in which the model asks for things: *look up `traje` in the
learner's store*, *search the external dictionary*, *fetch the sibling sense*.

Against it, specifically here:

- **The provider package has no tool-call shape.** `text()`, `chain.walk`, `chain.stamped` and
  `cooldown` would all need a second path, and requiring tool support would make every row without it
  unusable for chat — against a chain design whose whole point is that the owner picks.
- **The retrieval a tool would perform is already local.** The replica is complete and on the
  device. The client can select the twenty neighbouring entries worth sending before the request is
  made, for free and offline. A tool call would fetch, slowly and over the network, something the
  caller already had in hand.
- **The dictionaries are already on screen.** If external entries are open, their text is what the
  reader is looking at. Sending it is one field, not a tool.

> ### DECISION
> **One model call per turn. One JSON object back. No tool loop.**
>
> **Because** every tool the loop would call is answerable from the replica before the request
> leaves, and the runtime that would host the loop is the wrong place for one. Requiring tool-call
> support would also narrow which models this can run against, which is a cost with no matching
> benefit today.
>
> **Revisit when** a question genuinely needs the *spoken-usage corpus* rather than the replica — that
> lives on the server, is too large to preload, and is the first real argument for a second hop.

### §3.3 · Where the conversation lives

> ### DECISION
> **In memory on the device, keyed by what is being discussed, resent whole on every turn, and lost
> on reload.**
>
> **Because** the core's test for whether something belongs in it is whether losing it would
> hurt, and losing a transcript costs nothing — the *article* is where the value landed. This also
> keeps the route stateless: no chat collection, no session store, nothing to synchronise, nothing
> to tombstone.
>
> The last **eight** turns are resent, and the article document is resent every turn — so after a
> proposal is applied, the model sees the applied article, not the one it was asked about.

---

## §4 · What is sent, and what it is told about it

The request is assembled on the device, because the device is where the record, the replica and the
dictionary text already are.

```
┌─ CHAT REQUEST ─────────────────────────────────────────────────────────────┐
│                                                                            │
│  subject   the article, as `yamlFor(article)` — the exact document the      │
│            YAML tab shows, ids and all. THE SOURCE OF TRUTH.               │
│                                                                            │
│  focus     "sense:kq2…" — which block was tapped, when one was. null else. │
│                                                                            │
│  reference the external dictionary text currently open beneath the          │
│            article, verbatim from `referenceTextOf`, with its source names. │
│            READ-ONLY CONTEXT. Never the subject of an edit.                │
│                                                                            │
│  neighbours  up to 20 of the owner's own entries in the same language —     │
│            headword + shortGloss only — chosen from the article's topics.  │
│            This is what makes "you already have `mareo`" possible.         │
│                                                                            │
│  turns     the last 8, oldest first.                                       │
└────────────────────────────────────────────────────────────────────────────┘
```

**The document is assembled on the device, not the server.** `yaml.ts` is the only place the
projection is understood; a server-side serialiser would be a second implementation of it, drifting
from the first the moment a field is added. So the device sends the document it already has. Nothing
is lost by this: the server still holds the credentials, still owns the prompt, still shapes the answer, and
still writes nothing — the document it receives came from that owner's own replica and goes nowhere
but into their own prompt.

### The hierarchy, stated to the model in as many words

This is the part that must not be left to inference. The external dictionaries are frequently worse
than the entry the reader is looking at — machine-extracted, unevenly edited, sometimes wrong about
register, often missing the sense that matters — and a model handed two documents with no ranking
will average them. The prompt says, close to verbatim:

> **The article** is the learner's own entry for this word, in the projection Acervo stores. It is
> the source of truth. They wrote or approved every line of it, it is glossed into their own
> languages, and some of its examples are sentences they personally met. It is the only thing you
> may propose changing.
>
> **The dictionaries**, when present, are external reference: third-party sources the learner happens
> to have open on the same screen, below their own entry. They are read-only — the learner cannot
> edit them and neither can you — and they are often poor. Use one to check a fact, to find a sense
> the article is missing, or because the learner is asking about something they read there. Never
> treat one as outranking the article, and never propose a change to one.

---

## §5 · The answer, and the edit language

One JSON object. No prose outside it, same as every other prompt in `prompts/`.

```jsonc
{
  "reply": "«el traje» is any outfit or suit — a business suit, a regional costume …",
  "followUps": ["Add that to the notes", "One more example", "How do I remember it?"],
  "proposal": {
    "summary": "Adds the contrast with «el traje» to the notes, and one example under sense 1.",
    "ops": [ /* … */ ]
  }
}
```

- **`reply`** is the answer, and most turns are only this. Short — it is read on a phone above a
  keyboard. Capped at ~1200 characters server-side.
- **`followUps`** are up to three one-tap next turns, ≤40 characters each. This is the single
  highest-value field on mobile: it is the difference between a feature you use standing on a train
  and one you use at a desk. Free — same call.
- **`proposal`** is present **only when the turn implies a change.** A question gets an answer and
  nothing else. The prompt says so explicitly, and `§5.3` says it again.

### §5.1 · Operations

A target is a flat token — `lexeme`, or `<kind>:<id>` — because a flat string is what models get
right. Every id must already occur in the document that was sent.

Every operation is an `op` and a `target`, and the parent is a named field rather than part of the
operation's name, because a `target` already says what a family of operation names would repeat:

```ts
type Target = "lexeme" | `sense:${string}` | `example:${string}` | `attestation:${string}`;

type EditOp =
  | { op: "set";     target: Target; field: string; value: unknown }
  | { op: "add";     target: "sense";       after?: string | null; value: SenseValue }
  | { op: "add";     target: "example";     in: string; fromAttestation?: string | null;
                     value: ExampleValue }
  | { op: "add";     target: "attestation"; ref: string; value: AttestationValue }
  | { op: "remove";  target: Target; reason?: string }
  | { op: "reorder"; target: "senses"; ids: string[] };
```

`target` names a record everywhere except on `add` and `reorder`, where the record does not exist
yet and it names a kind. This is legibility rather than accuracy — the old names worked — and it is
cheap precisely because `§3.1`'s escape hatch is real: the marks are computed from drafts, so the
operation language is a detail of one request.

Settable fields, and nothing else:

| Target | Fields |
| --- | --- |
| `lexeme` | `headword` `lemma` `reading` `ipa` `pos` `gender` `register` `dialect` `emoji` `shortGloss` `notes` `topics` `status` |
| `sense:…` | `definition` `definitionLang` `domain` `glosses` |
| `example:…` | `text` `translation` `note` `matchedForm` `matchedTranslationForm` |
| `attestation:…` | `text` `translation` `sourceTitle` `sourceUrl` `sourceKind` |

`language` and `id` are not settable. `revision`, `editedAt`, `editedBy`, `deleted` and `ownerId` do
not appear in the projection at all and therefore cannot be addressed. Study state is written into
the YAML as comments (`yaml.ts`) precisely so it cannot be saved back by accident, and it is
likewise invisible here. Pictures are their own stage ([`sense-images.md`](sense-images.md)) and
are out of scope for chat.

### §5.2 · Two rules the data model imposes

**Ids are minted by the device, never by the model.** A document editing a stored entry may not carry ids
its producer minted, and an unknown id there is refused
([`../architecture/data-model.md`](../architecture/data-model.md)). So an `add` carries **no id**: the
applier leaves it null and `saveArticle` mints it, exactly as for a hand-written block with no id. Where
a new example must name a new attestation, the attestation's `add` carries a **`ref`** — an arbitrary
short label — and the example's `add` carries `fromAttestation: "<ref>"`. The applier resolves the ref
locally and mints both ids together, which is what the `minted` argument to `saveArticle` exists for.

**Provenance is modelled, not flagged.** An example the model wrote gets `origin: "llm"` and the
`modelId` of the model that wrote it. A sentence the *owner* supplied in the conversation is an
attestation, and the example drawn from it gets `origin: "attestation"` and names it. The model does
not set `origin` at all — the applier derives it from which operation created the example. There is
no field meaning "a person wrote this", and chat does not get one.

```jsonc
// "I heard this on the radio: «Se disfrazó de médico para entrar.»"
[
  { "op": "add", "target": "attestation", "ref": "a1",
    "value": { "text": "Se disfrazó de médico para entrar.",
               "translation": "He dressed up as a doctor to get in.",
               "sourceKind": "video", "sourceTitle": "Radio" } },
  { "op": "add", "target": "example", "in": "kq2m7x1p4vd9r0s", "fromAttestation": "a1",
    "value": { "text": "Se disfrazó de médico para entrar.",
               "translation": "He dressed up as a doctor to get in.",
               "matchedForm": "disfrazó", "matchedTranslationForm": "dressed up" } }
]
```

### §5.3 · Small, or nothing

Verbatim from the prompt, because this is where the feature either stays trustworthy or stops
being one:

> An edit changes the smallest thing that is wrong or missing: one field, one example, one note.
> You are not rewriting the article and you must not produce one.
>
> - Never touch a record the turn did not ask about.
> - Never restate an existing sense in your own words because you would have phrased it
>   differently. The learner's article is not a draft of yours.
> - If the honest answer is "nothing needs to change" — including "no, that is not an error, it is
>   how the word works" — say so and return no proposal. That is a good answer and the most common
>   correct one.
> - If what they want genuinely requires the article to be rebuilt, say so in `reply` and propose
>   nothing. That is a different action and they will choose it themselves.

Enforced, not merely asked for: **at most twelve operations**, and a proposal touching more than
half of the article's records is refused by the device with *"that was a rewrite rather than an
edit, so nothing was changed"*. A cap the model cannot argue with is worth more than a paragraph it
can.

### §5.4 · The reference subject

When the subject is an external entry rather than one of the owner's own words, the shape changes
and the prompt is a different tracked file. There is no `proposal`, because there is nothing
editable on screen. There is instead:

```jsonc
{ "reply": "…", "followUps": ["…"],
  "capture": { "headword": "el disfraz", "referenceMode": "expand",
               "note": "contrast it with «el traje»; they asked about theatre use" } }
```

`capture` is not a write and not a second pipeline. It is the argument list for the capture the
interface already performs from an external article: it becomes a `CaptureSeed`, `AddView` opens
and processes it, and everything downstream — resolve, compose, review, `saveArticle` — is
unchanged. Note what is *not* sent onward: the transcript. The model writes the `note` because it
knows what in the conversation mattered; shipping the raw thread would mean changing
`CaptureRequest` and teaching `acervo_compose` to read a conversation. One sentence does the job.

---

## §6 · Applying, showing, saving, undoing

Nothing new is invented on the write path. The whole pipeline is existing parts in a new order:

```
   ops ─────────────────────────────────────────────┐
                                                    ▼
  yamlFor(article) ──► parseArticle ──► draft ──► applyOps ──► draft'
    (the document                        │                       │
     that was sent)                      │                       ▼
                                         │                yamlForDraft ──► text'
                                         │                                   │
                                         └──────── diffDrafts ───────┐       │
                                                                     ▼       ▼
                                                      marks ─► articleFromDraft
                                                                     │
                                                                     ▼
                                                            LexemeArticle  (review)
                                                                     │
                                              ┌──────────────────────┴────────────┐
                                              ▼                                   ▼
                                   saveArticle(parseArticle(text'))          discard
                                       — the one writer —
```

Two new pure functions, in one new module `web/src/articleEdit.ts`, beside `selectors.ts` and
`yaml.ts` and pure like them:

- `applyOps(draft, ops): ArticleDraft` — all-or-nothing. An id that is not in the draft, a field
  that is not settable, a value of the wrong type, a `ref` that resolves to nothing: the whole
  proposal is refused with one plain sentence. No partial application, ever.
- `diffDrafts(before, after): DraftDiff` — record id → `added | changed | removed`, plus the set of
  changed fields on the lexeme head, plus removed records carried over whole from `before` so they
  can still be drawn.

**The marks come from `diffDrafts`, not from the operations.** That is what makes `§3.1`'s escape
hatch real, and it also means a hand-edit in the YAML tab could be marked by the same machinery if
that ever proves useful.

### §6.1 · Rendering a proposal is already a solved case

`AGENTS.md` warns: *do not render articles by round-tripping stored records through YAML text; the
projection is for editing and serializing, not for display.* Reading a stored article stays
`articleFor(graph, id)` and always will. But a proposal is **not a stored article** — it is an
unsaved document under review, which is exactly the case `articleFromDraft` exists for and exactly
what `AddView` already does with a generated entry. A live proposal puts the article view into
`AddView`'s regime for as long as it lasts, and leaves it the moment the proposal is saved or
discarded. Same component, same rule, no third feeder.

### §6.2 · A diff for someone who is not an engineer

No side-by-side, no unified diff, no `+++`/`---`. The article renders normally and the changed parts
say so in the margin — Notion's approach, in Acervo's marks and Acervo's palette.

```
  ✎ 3 changes proposed                          [ Discard ]  [ Save changes ]
 ─────────────────────────────────────────────────────────────────────────────

        🎭   el disfraz
             /disˈfɾaθ/   ▷ Listen
             n. · m. · es

  01 ───  Traje que se usa para parecer otra persona o un personaje.
  Sense   en · costume · disguise

          ┌ El disfraz de pirata viene con un garfio.
          │ The pirate costume comes with a hook.

       ┃+ ┌ Alquiló un disfraz de médico para la fiesta.
       ┃  │ He rented a doctor costume for the party.
       ┃  │ llm · gemini-3.1-flash-lite · unapproved

  ✎ ───   Notes
       ┃~ • «el traje» is any outfit or suit; «el disfraz» is worn to be taken
       ┃    for someone or something else.
       ┃✂ • Common around Carnival.
```

- `┃+` added · `┃~` changed · `┃−` removed · `┃↕` moved. A removed block is **drawn where it was**,
  struck through — nothing vanishes without being seen going.
- `−` rather than a scissor glyph, which is a smudge at 11px in the mono face and does not pair with
  `+`. The glyph is absolutely positioned in the gutter the block already owns and is never inside a
  paragraph: **no mark may change where body text sits**, and jsdom does no layout, so no test can
  catch a regression. `moved` is its own mark, because otherwise a reorder produces no marks and a
  count of zero over an article that has visibly renumbered itself; which senses moved is the
  complement of the longest increasing subsequence, so rotating three senses is one change.
- **A changed field carries a word-level diff**, computed on the device: the words that went struck
  through in `--warn`, the words that arrived in `--core`. Without it `changed` said only that
  something moved, and a reworded note — matched by text — read as a deletion beside an addition
  rather than as one change. No model is asked what it did: a model's account of its own edit is one
  more thing that can be wrong. **Word level, not character level, and hand-written** (`wordDiff.ts`)
  rather than a dependency, because the same `lcs` also finds the minimal set a reorder moved — the
  complement of the longest increasing subsequence, so rotating three senses is one change — and
  measures how alike two notes are. The tokeniser is `Intl.Segmenter`, because `\p{L}+` makes a Han
  sentence one token and the diff would report "everything replaced" for exactly the languages a
  learner needs it in most.
- **Where a block has no spare gutter** — a note, whose 15px holds an em-dash — it borrows 14px from
  the pane with an equal negative margin and pins the dash back, so the content edge does not move.
  *Rejected:* replacing a marked note's em-dash with the mark; the note stops looking like a member
  of its own list, and 3px of bar plus 7px of glyph does not fit in 15px anyway. The rule lives in
  the stylesheet above the `.mark` block, because jsdom does no layout and no test can catch it.
- **Only the field that changed is tinted** on a large block. A changed definition tints the
  definition and the sense keeps its rail bar; tinting the whole section would claim its untouched
  examples had changed. Small blocks — an example, an attestation, a note — tint whole.
- Colour: added and changed take `--core-soft`, removed takes `--warn-soft` with strikethrough.
  Existing tokens, correct in both themes, no red/green added to a palette that has neither.
- The mark is the *only* addition. The example still renders through `ExampleBlock`, still shows
  `llm · <model> · unapproved`, and still looks like the article it is about to become.
- The review bar is sticky at the top of the pane for as long as a proposal is live, the pane
  scrolls to the first mark when one arrives, and `‹ 1/3 ›` steps through the rest in the order the
  article draws them. It never wraps: on a phone the sentence shortens rather than taking a second
  row of a screen that has none to spare.

Deliberately left unmarked: **`matchedForm`**, because `realign()` may drop it as a side effect of
setting `text`, so marking it would report a change nobody asked for; and a marked example's
**`.ex.own` teal**, which gives way to the mark for the length of the review — the `origin` chip still
says `attestation`, and one signal per gutter is the limit. There are no keyboard shortcuts for next
and previous: they would fight the composer, which is where the hands already are.

**The YAML tab shows the proposed document and does not mark it.** The reason is that the YAML tab
is the escape hatch, not the review surface: someone who opens it wants to edit the text, and
gutter decorations there are answering a question the Article tab already answered. (CodeMirror
would make a tinted gutter nearly free, so this is a cheap thing to add later if it turns out to be
missed — but not first.)

### §6.3 · Saving, staleness, and undo

- **Saving** is `saveArticle(parseArticle(text'))`. Identical to saving a hand-edited document:
  same validation, same id diffing, same online-only synchronous round trip, same revision check.
  A chat-driven edit is indistinguishable downstream from a typed one, which is what keeps the core's regeneration promise honest.
- **A stale entry is refused, not merged.** If sync moved the record while the conversation was
  open, the write is refused by the server exactly as any other stale write is. The message says the
  entry changed elsewhere and the proposal is dropped.
- **A proposal is dropped** when the entry is hand-edited, when sync brings a new revision of it, or
  when the reader leaves the article. It is a suggestion, not a state.
- **Undo is the previous document, saved again.** The pre-edit text is held for the length of the
  session; undoing is one more `saveArticle`. This works without any special support because
  removed children are tombstoned rather than erased and `repository.stamp` sets `deleted: false` —
  naming a tombstoned id in a document brings the record back, id intact. Undo is offered as a
  single action on the toast after saving, and it is an ordinary online write like everything else.

---

## §7 · The interface

The hard constraint is not the laptop. It is a phone in portrait with the keyboard up, where the
usable height is roughly 300–380 px, and both the article and the conversation have to be legible in
it. Every product surveyed in `§2` solves the wide case and degrades the narrow one into a
full-screen chat that hides the document. That is the one outcome to avoid, because on the device
where the document is hardest to see is exactly where hiding it hurts most.

### §7.1 · One surface at every width

> ### DECISION
> **An ask dock pinned to the bottom of the article pane, which grows upward into a sheet. One
> component, one set of states, at every width. No side pane, ever.**
>
> **Because** the article column is 780 px (`.pane`; `--measure` is declared in the stylesheet and
> unused, so CSS written against it would do nothing) and a tablet in portrait — the primary reading
> device here — is about 834 px wide. A docked side pane would cut the article to
> roughly 400 px to make room for a conversation that is usually two turns long. The dock costs the
> article nothing horizontally at any width, and on a phone it *is* the mobile design rather than a
> degraded version of a desktop one.
>
> **And:** the answer to an editing turn is not a chat message. It is the article. The sheet
> collapses when a proposal arrives.

### §7.2 · Wide — tablet landscape, macOS

```
┌─ A. ─┬──────────────────────────────────────────────────────────────────┐
│      │  ⌕ Search your words…              + Add    ⟳ synced   ⚙   🇪🇸 ES │
├──────┼──────────────────────────────────────────────────────────────────┤
│ 📖   │  ←   Food                                 [ Read | YAML ]   ✎  🗑 │
│ 📥 3 ├──────────────────────────────────────────────────────────────────┤
│ ───  │                                                                  │
│ 🍲   │          🎭   el disfraz                                          │
│ 🧥   │               /disˈfɾaθ/   ▷ Listen                               │
│ 🏛   │               n. · m. · es                                        │
│      │                                                                  │
│      │     01 ───  Traje que se usa para parecer otra persona.      [✳] │
│      │     Sense   en · costume · disguise                              │
│      │             ┌ El disfraz de pirata viene con un garfio.      [✳] │
│      │                                                                  │
│      │     ✳ ────  Where you met it                                     │
│      │     📖 ───  Other dictionaries · 3                            ▸  │
│      │                                                                  │
│      │        ┌──────────────────────────────────────────────┐          │
│      │        │ ✳  Ask about this word…               ⌥⏎  ➔  │          │
│      │        └──────────────────────────────────────────────┘          │
└──────┴──────────────────────────────────────────────────────────────────┘
                the dock — pinned to the pane, at the article measure
```

`[✳]` is the anchor affordance, shown on hover or focus beside a sense and an example. Tapping one
sets a **focus chip** in the dock — `about sense 1 ✕` — which both prefixes the turn and tells the
model to keep its edits inside that record. This is Notion's selection-conditioning and Google
Docs' anchoring, and it is worth more on a phone than on a laptop: it removes the need to type
*"the second example"*.

Open, mid-conversation — the sheet shares the pane's bottom edge and the article scrolls behind it:

```
│     01 ───  Traje que se usa para parecer otra persona.               │
│                                                                       │
│    ┌──────────────────────── ⌃ ───────────────────────────┐           │
│    │                                        Clear    ✕    │           │
│    ├──────────────────────────────────────────────────────┤           │
│    │  you   How is this different from «el traje»?        │           │
│    │                                                      │           │
│    │  ✳     «el traje» is any outfit or suit — a business │           │
│    │        suit, a regional costume. «el disfraz» is     │           │
│    │        worn to be taken for someone else: carnival,  │           │
│    │        theatre, a party. You already have «el traje» │           │
│    │        under Appearance.                             │           │
│    │                                                      │           │
│    │        ┌ ✎  Add that contrast to the notes ────────┐ │           │
│    │        │    1 change · notes            Review  ▸  │ │           │
│    │        └───────────────────────────────────────────┘ │           │
│    │                                                      │           │
│    │  [ one more example ]  [ how do I remember it? ]     │           │
│    ├──────────────────────────────────────────────────────┤           │
│    │  about sense 1 ✕ │ Ask…                        ➔     │           │
│    └──────────────────────────────────────────────────────┘           │
```

The proposal arrives as a **card in the thread, not as an applied change.** Pressing *Review*
applies it to the draft, collapses the sheet to the dock, and scrolls the article to the first mark
— `§6.2`. Nothing is written until *Save changes*.

### §7.3 · Narrow — a phone with the keyboard up

Three detents: **dock** (the bar alone) → **open** → **full** (the thread alone, with the masthead
pinned above it as a context strip so the word being discussed is never off screen).

`open` is content-sized with a cap, so a fresh conversation is one line and grows turn by turn rather
than reserving a large empty box the moment the composer is focused. `full` takes the pane and the
article is not drawn at all, at every width: a sheet that stops short of the top leaves a useless
strip of article above it, on a desktop as much as a phone. The focus chip sits on its own row above
the composer, at every width, because inline it left an Android field about 180px wide.

`full` uses `.main.composing`, which already existed for the YAML editor and the Add view — *a surface
that owns the height and scrolls itself must not sit inside a region that also scrolls.* `overflow:
hidden` clamps `scrollTop` to zero, so the article's offset is parked on the way in and restored on
the way out. *Rejected:* `position: fixed` with insets, because `.viewport` sets `container-type:
inline-size` and so becomes the containing block for fixed descendants, and the insets would have to
clear a top bar on one layout and a top bar plus a rail of changing height on the other. The Add view
has no `full` detent: that surface is itself a review, and its composer already owns the height.

```
┌───────────────────────────┐   ┌───────────────────────────┐
│ ⌕ Search…      +  ⟳ ⚙ ES  │   │ ⌕ Search…      +  ⟳ ⚙ ES  │
│ 📖 📥 │ 🍲 🧥 🏛 …        │   │ 📖 📥 │ 🍲 🧥 🏛 …        │
├───────────────────────────┤   ├───────────────────────────┤
│ ←  Food      [ Read|YAML ]│   │ ✎ 3 changes    Discard    │
│                           │   │                    Save   │
│   🎭  el disfraz          │   ├───────────────────────────┤
│       /disˈfɾaθ/          │   │   🎭  el disfraz          │
│       n. · m. · es        │   │                           │
│                           │   │ 01 ─ Traje que se usa …   │
│ 01 ─ Traje que se usa …   │   │      ┌ El disfraz de …    │
│      en · costume         │   │   ┃+ ┌ Alquiló un disfraz │
├───────────────────────────┤   │   ┃  │ de médico para la  │
│ ⌃                      ✕  │   │   ┃  │ fiesta.            │
│ you  how is it different… │   │                           │
│ ✳ «el traje» is any out-  │   │ ✎ ─  Notes                │
│   fit or suit; «disfraz»… │   │   ┃~ • «traje» is any …   │
│                           │   │                           │
│ [ add to notes ]          │   ├───────────────────────────┤
│ [ one more example ]      │   │ ✳ Ask about this word… ➔ │
├───────────────────────────┤   └───────────────────────────┘
│ sense 1 ✕│ Ask…       ➔  │      after Review: the sheet is
├───────────────────────────┤      back to a dock, and the
│  q w e r t y u i o p      │      article IS the answer
│   a s d f g h j k l       │
└───────────────────────────┘
```

What makes this work on a phone, in order of importance:

1. **The answer is the article.** The sheet is a launcher and a reading surface for prose; the
   moment there is a change to look at, it gets out of the way. Most of what the reader looks at is
   the entry, not a transcript.
2. **`followUps` and the focus chip.** Two taps replace two sentences of typing. This is the
   difference between a feature used on a train and one used at a desk.
3. **Only the last turn or two above the keyboard.** The thread is bottom-anchored; the composer is
   docked; the scroller carries bottom padding equal to the composer plus the safe-area inset.
4. **The masthead stays.** At the `full` detent the article is hidden but the word is not.

**The keyboard needs real work, and the app does none of it today.** `web/index.html` has no
`interactive-widget` directive and nothing reads `visualViewport`. Both are required: add
`interactive-widget=resizes-content` to the viewport meta, and drive the sheet's bottom offset from
`visualViewport` for iOS Safari, which does not honour the directive. Without this the composer
lands under the keyboard on exactly the device this feature is for.

### §7.4 · States

```
  idle ──ask──► thinking ──┬──► answer ─────────────────────────────► idle
   ▲                       │      │                                     ▲
   │                       │      └─ proposal card ──review──► marked ──┤
   │                       │                                    │  │    │
   │                       │                     save ──────────┘  │    │
   │                       │                     discard ──────────┘    │
   └───────────────────────┴── failed (offline · refused · unusable) ───┘
```

- **thinking** — a quiet line in the thread, not a spinner over the article. The article stays
  readable and scrollable throughout; nothing about a pending turn locks it.
- **failed** — offline is an ordinary state, phrased as one: *"Chat needs the server. Your words are
  all still here."* Reading never depends on it.
- **marked** — the only state that changes what the article looks like, and it is always reversible
  with one press.
- The dock is disabled with that same sentence when the server is unreachable, and hidden entirely
  when the server reports no model configured — the capture surface already knows how to say this.

### §7.5 · The prototype

`AGENTS.md` binds `web/src/styles.css` to `design/ui-prototype/`: they change together, never one
alone. The dock, the three detents, the proposal card, the diff marks and the review bar all land in
`acervo.css` and in the prototype in the same change — `renderAsk` beside `app.js`'s `renderArticle`.
The one legitimate
divergence stays where it is — the prototype has no bundler, so its editor pane remains a picture.

One new mark is needed in `icons.tsx` for the dock and the anchor affordance. `✳` is already the
article's own mark for *where you met it*, so the ask affordance should not reuse it — a distinct
glyph, chosen with the prototype.

---

## §8 · Four entry points

### §8.1 · Your own article — the primary case

Everything above. The dock is present on every stored article, in `Read` mode, at every width.

### §8.2 · An external article

Same dock, same sheet, different prompt and no proposals. The subject is the dictionary text; the
owner's replica is not sent, because they do not hold this word. The only action the model can
offer is `capture` (`§5.4`), which surfaces as a card:

```
 │  ✳  Two of the three dictionaries have this as a nautical term;  │
 │     the third has only the figurative sense. If you keep it,     │
 │     the nautical sense is the one worth having first.            │
 │                                                                  │
 │     ┌ ✚  Add to my words ──────────────────────────────────┐     │
 │     │    with what you asked for            Add  ▸         │     │
 │     └──────────────────────────────────────────────────────┘     │
```

Pressing it opens `AddView` with a `CaptureSeed` whose `note` the model wrote. That is the existing
"Add to my words" path with one field filled in — no new writer, no new route, no second pipeline.
The entry still goes as `reference`, never as `text`, so a dictionary's examples still cannot become
attestations.

### §8.3 · A capture that is already held — the fold-in

A capture of a word already held stops at the duplicate, and **folding it in needs no extra model
call.** The resolve step has already returned `resolution.sentences`: the learner's own sentences,
corrected and separated from anything a dictionary supplied. So at the duplicate branch the server
already knows whether the capture carried anything the stored entry does not have.

```
        capture text
             │
             ▼
      resolve  ── returns language, headword, lemma, sentences ──┐
             │                                                   │
        duplicate?                                               │
        ┌────┴─────┐                                             │
       no          yes                                           │
        │           │                                            │
        │      anything to fold in?  ◄──────────────────────────-─┘
        │      (a sentence · a dictionary reference · a note)
        │           ┌──────┴───────┐
        │          no             yes
        │           │              │
        ▼           ▼              ▼
     compose    "You already   "You already have this — fold your
     → review    have this."     sentence into it?"   [ Open ] [ Fold in ]
                 (unchanged)             │
                                         ▼
                          opens the stored article with the chat
                          seeded: "Fold this in: «…»" — one turn,
                          one proposal, reviewed and saved like
                          any other.
```

The capture response carries `foldable: { sentences, reference }` or null, and the duplicate panel in
`AddView` has one button for it. Two model calls in all, exactly what composing a new entry costs. *A
repeat capture is an addition, not an entry* ([`capture.md`](capture.md)), and it needs no merge path,
no second writer, and nothing the chat does not already do.

### §8.4 · A proposal under review, before it is saved

The same dock on `AddView`'s Article tab. The draft carries the ids `draftFrom` minted, so the
operations address it exactly as they address a stored one; the ops are applied to the draft, the
YAML is regenerated, and the tab re-derives as it already does on every keystroke. Instead of
re-running generation and losing what was right, one sentence changes one thing. It is the least
valuable of the four entry points and the one most likely to want a different diff treatment, since
everything in a fresh proposal is new.

---

## §9 · Protocol

`POST /api/acervo/v1/chat` — authenticated, owner-scoped, online-only, **writes nothing**.

```ts
export interface ChatTurn { role: "you" | "acervo"; text: string }

export interface ChatRequest {
  schemaVersion: number;
  deviceId: string;
  subject:
    | { kind: "article"; lexemeId: string; document: string; focus: string | null }
    | { kind: "reference"; headword: string; language: string | null };
  /** External dictionary text on screen. Read-only context for both subject kinds. */
  reference: string | null;
  referenceSources: string[];
  /** From the replica: the owner's own neighbouring entries, headword and gloss only. */
  neighbours: { headword: string; shortGloss: string | null }[];
  turns: ChatTurn[];
}

export interface ChatResult {
  reply: string;
  followUps: string[];
  proposal: { summary: string; ops: EditOp[] } | null;   // article subjects only
  capture: { headword: string; note: string; referenceMode: "faithful" | "expand" | null } | null;
  modelId: string;
}
```

- Timeout `CAPTURE_TIMEOUT` (120 s) — one model call, but a slow one, and the sync timeout would
  abort a request that is working. Same reasoning that already applies to capture.
- Limits, enforced server-side and stated in the prompt: `document` ≤ 32 KB, `reference` ≤ 8 KB
  (`REFERENCE_LIMIT`, already defined), `turns` ≤ 8 after truncation, `neighbours` ≤ 20, `ops` ≤ 12,
  `reply` ≤ 1200 characters, `followUps` ≤ 3 × 40 characters.
- Errors reuse the existing codes exactly: `capture_unavailable` when no model is configured,
  `llm_unreachable`, `llm_failed`, `llm_empty`, `llm_unusable`. Every message ends in *"so nothing
  was changed"*, matching the capture route's *"so nothing was created"*.
- Model: chat is a text call and answers on the owner's **text** chain — `chain_for(settings, owner, "text")`, resolved per
  request, so Settings ▸ Providers takes effect on the next turn with nothing restarted. If chat later
  proves to want a different model, the shape is another `kind` in the catalogue, justified by a
  measurement rather than assumed. There is no per-feature model variable.
- Rate: no per-owner floor. The route is authenticated and owner-scoped, one model call per turn,
  and a provider's own limit surfaces as `llm_rate_limited` with `models/cooldown.py` resting the
  row. If a floor is ever wanted it belongs beside `model_selection` as an unreplicated table, not in
  the route.

### Prompts

Two new tracked files in `prompts/`, copied into the image and read at request time like the
existing pair. They are content, not code — changing what the chat says must not mean changing the
hook.

- `prompts/acervo_chat.md` — the article conversation: the hierarchy (`§4`), the operation
  language (`§5.1`), the provenance rules (`§5.2`), and "small, or nothing" (`§5.3`).
- `prompts/acervo_chat_reference.md` — the external-entry conversation: read-only throughout, no
  operation language at all, and the one action it may offer is a capture.

Two files rather than one with a mode switch: they are genuinely different jobs with different
output shapes, and the shorter one shares none of the longer one's edit language.

---

## §10 · Where the line falls

Chat is a **consumer of the core** ([`../README.md`](../README.md). Concretely, it does not get:

- **Storage.** No collection, no `sync_state` entry, no tombstones, nothing replicated. The
  transcript is in memory and is lost on reload, on purpose.
- **A second writer.** Every change goes through `repository.saveArticle`, online, at the record's
  revision, refused if stale.
- **A second article format.** Operations are a wire format for one request. They are applied to an
  `ArticleDraft` and then they cease to exist.
- **A second serialiser.** `yaml.ts` remains the only place the projection is understood.
- **Agency.** Nothing is applied without a press, nothing is written without a second press, and
  every write is undoable with a third.
- **The whole vocabulary.** *"Which of my words are like this one"* across the entire store is a
  different feature with a different shape — the set difference against what you actually hold
  ([`../plans/word-discovery.md`](../plans/word-discovery.md)). Chat sends at most
  twenty neighbours and says so.
- **Offline anything.** A turn is a server round trip; reading the article never is. The dock is the
  only part of the article view that ever reports the server being down.

---

## §11 · What a real model does

Three behaviours only a live run shows, each now handled in the prompt or the code:

- **`fromAttestation` arrives in two shapes.** A real model puts it inside `example` about half the
  time. Missing it is *silent*: the applier would derive `origin: "llm"` for a sentence the learner
  actually met, and nothing downstream would notice the entry lying about where it came from.
  `services/chat.py` lifts it from either place, and the prompt says which one is right and why.
- **A comparison question reliably proposes.** Asked "what is the difference between X and Y?", a model
  offers to add the contrast to the notes, however firmly the prompt says a question gets prose. So the
  contract held is not "never volunteer" — a proposal is **offered**, not applied, and nothing is
  written without a press on *Review* and a second on *Save*, so an unasked-for proposal is a
  pre-computed follow-up. It is **never rewrite what is already there unasked**:
  `test_it_answers_a_question_without_rewriting_anything` allows at most two operations, no invented
  ids, and only additions to the notes that keep every line already there. The prompt still asks for the
  stricter behaviour, because the guidance is right where the model is unreliable, and a coin-flip
  assertion is worse than an honest one.
- **Over-correcting loses volunteered sentences.** Pushed too hard, *"I heard this on the radio: «…»"*
  stops being proposed. The prompt carries an explicit two-column gate — the turn on the left,
  `proposal` or none on the right — with volunteered sentences marked **yes**, *because they went to
  the trouble of typing it*.

**Acknowledgements are banned as follow-ups**: *"Looks good"* spends the one one-tap slot a phone has on
nothing. The prompt forbids them and `_shaped` drops one whose whole string, casefolded and stripped of
punctuation, is in a fixed set — whole-string only, so *"Thanks, now add an example"* survives.

### Verification

```
npm --prefix web run test         # articleEdit.test.ts is the new one that matters:
                                  #  · ops applied in order; unknown id refuses the whole set
                                  #  · a `ref` resolves; the example gets origin "attestation"
                                  #  · an added example gets origin "llm" and the model id
                                  #  · no op may set language or id; >12 ops refused
                                  #  · a proposal touching over half the records refused
                                  #  · parseArticle(yamlForDraft(applyOps(…))) round-trips
                                  #  · diffDrafts marks added / changed / removed by id
.venv/bin/python -m pytest tests/unit/server  # the chat route against a temporary database:
                                  #  · no key → capture_unavailable, nothing else attempted
                                  #  · transcript truncated to 8; document and reference capped
                                  #  · a reference subject never returns ops
                                  #  · a malformed answer → llm_unusable, "nothing was changed"
npm --prefix web run test         # App.test.tsx: dock renders on a stored article, a proposal
                                  # renders marks, Save calls the repository once, Undo saves back
```

Manual, on the devices this is for:

- iPhone, PWA, keyboard up: composer above the keyboard, last turn visible, the masthead never off
  screen, the article scrollable while a turn is pending.
- iPad portrait: the article keeps its full measure with the dock present — the check the side-pane
  decision in `§7.1` exists to pass.
- Server stopped: the article reads normally, the dock says the server is needed, nothing is lost.
- Sync the same entry from a second device mid-conversation, then save: refused, plainly, and the
  proposal is dropped.
- Save, then Undo: the removed example comes back with its original id.

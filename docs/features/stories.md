# Stories · a handful of words told back as an illustrated tale

A story takes one to eight of the owner's words — three by default, from the words on screen or the
ones marked by hand — and returns four to six parts, each a paragraph, its translation and a picture,
read aloud in one voice. It is read as a deck. The package is `src/acervo/stories/`, which stands
alone on `acervo.models` like `images/`; `services/stories.py` is the binding layer; the job is
`work/story.py`. Whether the pipeline holds its shape was settled in
[`experiments/story-quality/`](../../experiments/story-quality/README.md); whether the stories are
*good* is the open question in [`../plans/quality/story-quality.md`](../plans/quality/story-quality.md).

---

## Asked for by a route, made by a job

`POST /stories` takes the word ids, a **kind** and a **style**, and an optional note in the owner's own
words (the "Anything else?" box), writes the story row, and queues a `story` job. The kinds are
tracked config (`config/story-types.yaml` — funny, historical, science, mystery, everyday and the
rest), the styles are the picture style table, and both are ids stored **on the story**, so Try again
writes the story that was asked for rather than quietly becoming a different one. The note is sent to
the writer only when present, and outranks the kind's direction but never the prompt's rules.

**The job is five steps, so four good ones survive a fifth that fails:**

| Step | Calls | Lane |
|---|---|---|
| `story.write` | one text call, hot (temperature 1.0), the whole story | text |
| `story.translate` | one text call, cold, the **whole** story at once, so a pronoun or a recurring name is translated consistently | text |
| `story.brief` | one text call covering **every part**, so a character keeps the same coat across four pictures | text |
| `story.draw` | one image call per part, all in the story's style | image |
| `story.audio` | the narration, below | audio |

**Its state is derived**, like a loop's: no parts means never written, a part with no `imageRef` is not
drawn, a part with no passages is not recorded. **Each of the first three steps skips itself when its
work is already in the graph** (`is_written`, `is_translated`, `is_briefed`), because Try again queues
every step again and the commonest failure is the last one — without the check a retry would write the
story a second time beside the first.

**One number in the interface.** `ProgressStrip.stripOf` collapses a story job to
`63% · Drawing picture 2 of 4`: the percentage first, from step weights and from the count
`story.draw` reports through the `progress` callable it is handed (`services/` does not know jobs
exist). The count is over every briefed part, so a retry carries on from what is already drawn and the
figure never runs backwards.

## Writing, and holding the writer to it

**The writer substitutes synonyms, and will report them as the word.** On the very first call, asked to
use `asombroso`, the model wrote a story without it and reported `sorprende` as the form it used. So the
forms it reports are verified against the text on the server, a word it could not work in is kept with
empty `forms` rather than dropped, and the prompt says so. `storyWords` records what the story was asked
to teach and the surface forms it actually used ([`../architecture/data-model.md`](../architecture/data-model.md)).

**Marks are found, not stored, in both languages.** `forms` are the surface forms the writer used, and
`translationForms` are the words of the translation that render each one, reported by the translator
and kept only where they appear verbatim in what it wrote; `storySpans` searches for either. The second
is a garnish on a good translation, so `stories/translate.parse_reply` reads it leniently: a missing or
malformed field costs the mark and never the translation, which is not declared unusable and passed to
the next model over a highlight. Empty is ordinary and marks nothing.

The owner's standing rules (Settings ▸ Rules) are appended to the write, translate and brief prompts,
and not to narration, which may not change a word.

## Pictures that keep their characters

**A story's later pictures are drawn from its earlier ones, chosen by who and where, never by position**
(`stories/continuity.py`). A small text call labels the stored briefs with the characters each puts in
frame and the one place it is set in, as ids. Part *k* is sent the **first** picture of each returning
character and the **last** of its place — at most **two**, characters before the place, and none when
nothing recurs.

- **The first picture of a character**, because anchoring a face to the latest picture lets it drift
  further with every part; **the last of a place**, because a place is meant to carry what happened to it.
- **Nothing when nothing recurs**, which is what keeps a story about two inventors from giving the second
  man the first man's face.
- **The labels are a separate call** over briefs already written, not more fields in the brief prompt:
  asked for ids as well, the brief writer stopped restating the cast, which a part drawn with no
  references depends on. The call is opportunistic — if it fails the story is drawn without references.
- **Whether a model can take references is per pair**, `capabilities.image.references` on its catalogue
  row; a pair without it is sent the plain brief. References go over LiteLLM's chat route, since
  `image_generation` takes no image for Vertex Gemini, and `prompts/acervo_story_reference.md` puts the
  picture first and the references second, because a conditioned photograph came out matching and
  stiffer the other way round.
- **Settings ▸ Stories** chooses `all` (the default), `artwork` (every style not marked
  `photographic: true`), or `off`. Measured blind in
  [`experiments/story-picture-reference/`](../../experiments/story-picture-reference/): references won
  8–0 in drawn and painted styles and lost 4–0 in the photoreal one on the first run, and with the
  reference prompt reordered won 7–0 with 3 ties in photographic styles on the second.
- **The pair that drew a story's first picture is moved to the head of the chain** for the rest, read
  back off the graph, and stepped over like a pinned voice when it is busy.

## Read aloud in one voice, one file to a passage

The recording is columns on `storyParts` — the voice that read it and a list of passages — rather than a
`pronunciations` row, for the reason a picture is not one: a pronunciation must name a word, and a part
is not a word. No passages is *not recorded*.

**With a directed voice**, one text call per part (`stories/narrate.py`, `prompts/acervo_story_narrate.md`)
cuts it into passages with a direction each, and one call to the voice per passage
(`prompts/acervo_pronounce_story.md`: a narrator, not "in the moment"). **With a clear voice**, one
passage covers the whole part, so the shape is the same either way and there is simply nothing to tap
below it. A directed story is read by whoever reads the expressive order, which is only pairs declaring
`style: instruction` — the rule every spoken thing follows
([`pronunciation.md`](pronunciation.md)), not one of the story's own. Where none can be reached, the
part is read whole in one call and no segmentation call is made: passages exist to carry a direction,
and four plain calls would cost four times one. If the directed voices run out partway through a part,
the passages still to record are read by the plain order one at a time, keeping their breaks and
carrying no direction; that is simpler than throwing the passages away and re-reading the part.

- **The model is never trusted with the words.** `narrate.tile` finds each returned passage in the
  original, in order, and whatever it left out, changed or reworded stays in the story as a passage with
  no direction — so what is spoken always joins back to the text exactly.
  [`experiments/story-audio-segmentation/`](../../experiments/story-audio-segmentation/) measured 25 clean
  answers in 25; `tile` is why the 26th would not be a wrong sentence.
- **Each passage is its own file, and nothing is ever seeked.** A browser seeks a compressed stream to a
  page boundary — a second, in the Ogg that libsndfile writes — and reports the position that was asked
  for rather than the one it gave, so a passage inside a joined file starts a word or two late or early
  with no way to detect it. A file that begins where the passage begins cannot be wrong, and playing from
  a passage to the end of a part is a queue of files.
- **The voice is fixed per story.** `services/story_audio` pins the first recorded part's (provider,
  model, voice), because a story that changed speaker between paragraphs would be worse than one that
  failed. But **a pinned voice is a preference, not a cage**: a pair that refuses for a reason that passes
  — a quota, an outage, a dropped connection — is stepped over and the next records the rest, since
  insisting cost a real story three silent parts on a free row whose allowance had gone. A rejected
  credential is raised instead.
- **A passage already paid for is never bought twice.** Masters go into the same content-addressed take
  store a loop uses, and a retry probes it for every pair the order offers, because a part is written
  only once all its passages exist and a tier of ten calls a day cannot afford to record the first two
  again.
- The job step and `POST /stories/{id}/parts/{part}/audio` are the **same function** (`narrate_part`):
  the step reads the `stories` switch in the pronunciation settings (on by default) and the route is
  what runs when it is off. Settings ▸ Stories writes the stories delivery order and that switch.
- `python -m acervo.admin stories show <id>` prints a story's parts, passages and directions — the one
  way to see whether a passage carries its direction or an empty one.

## The reader

**A story is read as a deck**, the same deck a word's cards are (`deck.tsx`): a native scroll-snap track,
so a swipe follows the finger and a trackpad scrolls it with no gesture code of its own; arrows beside the
column when the margin measures at least 100 px and under it otherwise; the arrow keys; the ivy leaf. The
layout follows the deck's own width (`@container deck`), never the window's: wide puts the picture beside
the words, narrow puts it above them with the free space split 1 : 1.618. The last page lists the words
the story was asked to teach, as the word list draws them, with the ones it could not work in dimmed
rather than dropped. The translation is hidden until asked for, and travels with the part, since a reveal
that waited on the network would not be a reveal.

**Playback** is `storyAudio.ts`, the third audio element, registered with the others so they stop each
other. **Pause is pause and leaving is stop**: there is no scrubber, and a page that stops being the one
on screen stops its part and forgets the position, so swiping away and back begins it again. **A tap on a
word looks it up and plays nothing** ([`look-up.md`](look-up.md)); the passage it is in is the sheet's
button, and a tap on anything else in a passage plays it. A passage started while nothing plays is played
alone; started while the part plays, the recording moves there and carries on. `segmentSpans` cuts the marks at the passages and refuses passages that do not join to the
text, so a recording made from words since changed paints nothing. The sounding passage is tinted with a
background, never padding, weight or size. Recordings are kept on the device with the other clips, so a
story plays on a plane.

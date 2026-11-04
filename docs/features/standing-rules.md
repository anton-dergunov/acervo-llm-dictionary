# Standing rules · telling every prompt something once

Settings ▸ Rules is free text the owner writes once — *"I am vegan, so never show or mention meat"*,
*"never use profanity in an example"* — and it reaches every model call that
writes something the owner will read. It is stored per owner in `prompt_rules`, server state that is
never replicated, and joined to prompts in one place, `services/rules.with_rules`.

---

## Where it goes, and where it deliberately does not

| Call | Rules appended | Why |
|---|---|---|
| Compose — writing an entry | yes | the definitions, notes and examples are read |
| The article conversation, both prompts | yes | its answers and proposals are read |
| Clip selection | yes | it chooses which real speech the owner hears |
| The picture brief | yes | it decides what a picture shows |
| A story's write, translate and brief | yes | all three write what is read and seen |
| Resolve | **no** | it only names the word a scrap of text is about |
| Story narration | **no** | it cuts a story into passages and may not change a word |
| Naming the map's regions | **no** | it only labels what is already there |
| Voices and image models | **never** | what they say and draw is what a text call already wrote |

## The reader: what one vocabulary says about its learner

Rules are the owner's, for everything. What differs from one language to the next — how well they read
it, which variety they learn, why they learn it — is the vocabulary's, set in Settings ▸ Vocabularies
([`settings.md`](settings.md) §6), and it reaches the writers as a second section, **"The reader"**,
joined in front of the rules by `services/reader.with_reader`. Each fact is said with its own weight,
firmest first:

| Fact | How it is said | Why |
|---|---|---|
| **Level** (`A1`…`C2`) | keep what you write within reach of it; a harder sentence only where the word needs one | a sentence out of reach teaches nothing |
| **Variety** (`region`) | prefer its words, forms and grammar where regions differ; **do not hide the others** and say what is said elsewhere; mark a word regional only when it is | a learner of Argentine Spanish still meets *vosotros* and *coger*; a preference, never a filter |
| **About you** (`learnerNote`) | background, not a subject: at most one example in an entry or one detail in a story, often none; never mentioned, never bent toward | told "a trip to Argentina", a writer asked for *cactus* must still write about cacti |

It goes where a writer writes in that language for the learner to read: **compose**, **the article
conversation** (both prompts, for the language the device names) and **a story's text**. Not the
story's translation, briefs or narration, the picture brief or the clip choice, whose subject is the
word or a text already written — and the note is exactly what would turn every picture toward
Argentina. The weights are measured, not argued: [`../../experiments/learner-context/`](../../experiments/learner-context/README.md)
sends the same words and stories with no section, this one, and the same facts stated flatly, and
counts how often an example about an unrelated word turns out to be about the note: 6% against 3% with
no section, and 1 of 9 stories against 5 of 6 when the facts are stated flatly. The wording that got
there says the note is **not material** — no character shares the learner's job or plans, nothing is set
where they are going — and that **the variety decides the words, not the setting**; "one detail in a
story", the first wording, was read as leave to make the hero a programmer in Buenos Aires.

With nothing set the section is absent and the prompt is byte-for-byte what it was, as with the rules.
A template whose request follows under its own heading (`## The request` for a story) has that heading
written by its pipeline package after the template, so nothing appended can land between a heading and
what it introduces.

## How it is joined

The rules are appended as **the prompt's closing section**, under a heading, with a short preamble:
follow them in what you choose to write about — subjects, scenes, examples, register — and never let them
change the shape of the answer asked for above. Said last, after everything the prompt asks for, so the
rules steer *what* is written and cannot be read as a change to the reply's format, which every caller's
parser depends on.

- **With no rules a prompt is byte-for-byte what it was.** Nothing is appended, not even an empty
  heading.
- **The joining is in the binding layer.** `with_rules` is applied in `services/` to prompt text a
  service has already loaded, so the pipeline packages — `images/`, `clips/`, `stories/` — are handed a
  prompt and never learn where part of it came from.
- **It is bounded**: 4,000 characters, shown as a count under the box.
- **It outranks nothing structural.** A story's own note from the owner outranks the story kind's
  direction; standing rules sit beside both and never override a prompt's rules about the shape of the
  answer.

## Why free text

The alternative is a growing panel of settings — a register, excluded subjects — each a column and a
branch in every prompt that reads it. The level is the one exception, and it is the vocabulary's: it
differs by language, every writer needs it, and a picker gives it a weight free text cannot. Free text costs no schema per preference, reads the way the
owner thinks about it, and applies to every call at once. It is also the first answer to taste questions
that would otherwise become per-feature knobs: how tidy a clip's speech should be is a sentence here
before it is a setting there ([`../plans/quality/clip-selection.md`](../plans/quality/clip-selection.md)
Part 2).

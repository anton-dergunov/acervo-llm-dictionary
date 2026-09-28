# Standing rules · telling every prompt something once

Settings ▸ Rules is free text the owner writes once — *"I am vegan, so never show or mention meat"*,
*"I read Spanish at about B2; keep examples at that level"* — and it reaches every model call that
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

The alternative is a growing panel of settings — a level, a register, excluded subjects — each a column
and a branch in every prompt that reads it. Free text costs no schema per preference, reads the way the
owner thinks about it, and applies to every call at once. It is also the first answer to taste questions
that would otherwise become per-feature knobs: how tidy a clip's speech should be is a sentence here
before it is a setting there ([`../plans/quality/clip-selection.md`](../plans/quality/clip-selection.md)
Part 2).

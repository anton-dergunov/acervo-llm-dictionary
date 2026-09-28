# Story generation: does the pipeline hold its shape?

**Question.** Not "are the stories good" — that needs a method this does not have, and it is
[`docs/plans/quality/story-quality.md`](../../docs/plans/quality/story-quality.md). This asks the cheaper questions
that had to be settled before any of it could ship, and that no stubbed test can reach:

1. Does the model hold the reply shape, and how often does `parse_reply` have to refuse it?
2. Does it actually use every word it was given — and report the forms **verbatim and honestly**?
3. Are the parts the length the reader was built for, or does a part have to be scrolled?
4. Does the translation come back with the same number of parts, in the same order?
5. Do the image briefs restate the cast, or do they say "the same man as before"?

**Method.** `run.py` calls the shipped prompts through the shipped package — `acervo.stories` —
against `gemini-free` (`gemini/gemini-3.5-flash-lite`), with stand-in Spanish words carrying the
definitions a real article would. No pictures are drawn; the briefs are what is under test.

**Cost.** Seven calls across three rounds. ~4.5 s and ~$0.002 for a story, ~1.2 s for a translation,
~1.8 s for a set of briefs. Every call held the JSON shape; `parse_reply` never had to refuse one,
and the chain never fell through.

---

## What it found

### 1. The model substitutes synonyms, and will report them as the word

The single most important finding, and it appeared on **call one**. Asked for a story using
`asombroso`, the model wrote a story in which that word never appears — and then reported
`sorprende` as the form it had used.

This mattered far more than a missing word. The reader marks the reported form in the text, so the
learner would have seen a *different word* highlighted and taught as the one they were learning. The
first version of `parse_reply` passed it, because it only asked "does this string appear in the
text", and `sorprende` does.

Two fixes, and both were needed:

- `write.is_form_of` now checks a reported form is plausibly an inflection of the word — shared
  four-character stem, or one containing the other. Deliberately shallow; it holds no language data
  and must not grow into a morphological analyser. Its false negatives are suppletive forms
  (`ir`/`fue`), which read as an unused word — visible and mild, where a false positive is silent.
- The prompt names the failure, the example, and tells the writer to read its own text back and look
  for each word before finishing.

After the fix, every word in every subsequent round was used literally and reported correctly,
including correct inflection (`hormigas` for `hormiga`).

### 2. Headings label the machinery, not the story

Round 2 produced `La llegada`, `El problema`, `La solución`, `El giro` — headings that would fit any
story ever written. The prompt had only forbidden *numbering* (`Parte 2`), which these technically
are not.

The prompt now names this second failure separately and gives the test: **if a heading could be
moved to another story without anybody noticing, it is not a heading.** Round 3 produced
`Golpes a medianoche`, `Una sombra en el tejado`, `El vecino nocturno`.

### 3. The brief writer draws the reaction instead of the subject

Round 2's third part is a column of ants crossing a roof. Its brief framed Clara's face in close-up
with the roof "blurred in the background" — the ants, which are what the part is *about*, were not
in the picture at all.

Left alone this produces four pictures of one person's face and no sense of what happened. The
prompt now says to put the subject in frame, and that a reaction shot is worth one picture in a
story and never the one where something is revealed. Round 3's final brief puts the raccoon among
the boxes, large and in focus.

### 4. What worked first time, and did not need touching

- **Cast consistency, which was the main risk.** Each picture is drawn by a model that has never
  seen the others, so the one-call-for-every-part design and the `cast` field carry the whole
  burden. In both rounds that were briefed, the character's description was copied into **every**
  brief verbatim — "cream-coloured wool cardigan" ×4, "dark blue cotton nightshirt" ×4. No brief
  ever said "as described above".
- **Framing variety**, also asked for once and delivered: window, look-up, close-up, look-down.
- **The translation call.** Same part count, same order, faithful, natural English, ~1.2 s. It never
  merged or split a part, which was the failure the count check exists for.
- **Part length.** Every part landed between 240 and 378 characters, 2–4 sentences — comfortably
  inside the 1200-character ceiling that exists so a part fits one screen.
- **Story type briefs.** `everyday` produced an ordinary morning with a real ending; `mystery`
  produced a fair-play mystery with a mundane solution. Both read as the kind they were asked for
  rather than as the same story relabelled.

---

## What is left, and deliberately not done here

- **Whether the stories are actually good.** Seven stories read by one person is not a measurement.
  `docs/plans/quality/story-quality.md` is the stub for doing it properly.
- **Forcing a word can bend the prose.** Round 3 produced `empezar a susurrar un gruñido bajo` —
  "to whisper a low growl", which is odd Spanish. Expected when a word must appear, worth watching,
  not worth a prompt rule yet.
- **The pictures themselves.** No image call was made. The briefs are the thing this could judge.
- **Other languages.** Everything here is Spanish. The stem check in `is_form_of` is the part most
  likely to behave differently elsewhere, and it is the thing to re-examine first.

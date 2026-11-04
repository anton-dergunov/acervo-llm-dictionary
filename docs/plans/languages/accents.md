# Accents · the rest of the app following a vocabulary's

**Status:** not started. What exists is the part every later step reads: a vocabulary carries its
accent (`vocabularies.region`, set in Settings ▸ Vocabularies), and the voices already follow it —
voices made for that locale rank first, and a voice that takes an instruction is told it
([`../../features/pronunciation.md`](../../features/pronunciation.md), "Accent, and which voice reads
first"). Everything else still writes and searches for the language as a whole.

What following the accent would mean, in the order it is likely to pay:

1. **The writer.** The compose prompt names the variety, so an Argentine Spanish article uses *vos*
   and its conjugations in examples, prefers *colectivo* to *autobús*, and marks a word that is
   regional elsewhere. This is a prompt change, so it is measured before it ships: on the real prompt,
   Flash Lite and a fixed set of words, against the current articles, with the variety-specific
   choices labelled by hand — the apparatus in `experiments/compose-lesson-line/` is the start. The
   risk to look for is the opposite mistake: a model told "Argentina" that turns every example into
   slang, or marks standard words as regional.
2. **Chat and stories.** The same instruction in `acervo_chat*.md` and `acervo_story_write.md`, and
   the same measurement. A story's narration already follows the accent.
3. **Clips.** A vocabulary with an accent could rank its own region's speakers first, which needs the
   corpus to know where each channel's speakers are from — whether it records that is to be checked
   first. Either way it is a change in `spoken-usage-retrieval` (a field on the search request), made
   there and re-pinned, not filtered on this side.

Two questions to answer before building:

- **Re-recording.** Changing the accent records nothing again, because a clip is stale only when its
  words change. Whether to offer "Record this vocabulary again in the new voice" — one `enrich`-style
  job over every recorded field — depends on how often the accent changes after words exist; until
  then "Record again" replaces one clip at a time.
- **Where a regional word is recorded.** A lexeme already has `dialect`; an article written for
  Argentina may mark a word as Spain's. Whether that is the same field read the other way round, or a
  second one, is decided with the writer change, not before.

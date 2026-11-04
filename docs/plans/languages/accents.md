# Varieties · the rest of the app following a vocabulary's

**Status:** what reads and writes the language follows the variety; what *finds* speech does not yet.
A vocabulary carries its variety (`vocabularies.region`, set in Settings ▸ Vocabularies). The voices
follow it ([`../../features/pronunciation.md`](../../features/pronunciation.md), "Accent, and which
voice reads first"), and so do the writers — compose, the article conversation and a story's text —
through the reader section, as a preference that never hides the other varieties
([`../../features/standing-rules.md`](../../features/standing-rules.md), "The reader").

What is left:

1. **Clips.** A vocabulary with a variety could rank its own region's speakers first, which needs the
   corpus to know where each channel's speakers are from — whether it records that is to be checked
   first. Either way it is a change in `spoken-usage-retrieval` (a field on the search request), made
   there and re-pinned, not filtered on this side.

Two questions to answer before building more:

- **Re-recording.** Changing the variety records nothing again, because a clip is stale only when its
  words change. Whether to offer "Record this vocabulary again in the new voice" — one `enrich`-style
  job over every recorded field — depends on how often the variety changes after words exist; until
  then "Record again" replaces one clip at a time.
- **Where a regional word is recorded.** A lexeme already has `dialect`; an article written for
  Argentina may mark a word as Spain's. Whether that is the same field read the other way round, or a
  second one, is decided from what the writer does with it in practice —
  [`../../../experiments/learner-context/`](../../../experiments/learner-context/README.md) counts
  `dialect` set on words that are not regional, which is where a confusion would show first.

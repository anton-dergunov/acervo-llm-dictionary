# Anki · what is still to do

**Status:** open. Cards go out by themselves a minute after the vocabulary changes, and review state
comes back per sense every hour ([`../features/anki.md`](../features/anki.md)). What is left is small:
look hard at the cards, show how hard a word is, and let a deployment do without Anki.

## 1 · Review the cards

A design pass on the cards themselves, done by the owner with the cards in hand rather than from the
design document: which kinds of card are worth having, what content is worth generating *for Anki*
that the article does not already carry, and how each face is laid out.

- **Start from what exists.** A sense's Produce card already cuts the word out of a sentence, which
  is the cloze; an example's Recognise card asks for the meaning in context; Listen asks by ear
  ([`../features/anki.md`](../features/anki.md), "The cards"). The question is what is missing or
  wrong, not whether to have these.
- **Content for Anki, if any.** A card may want something an article does not — a shorter sentence, a
  harder one, a cue that stops the answer being guessed from the picture. Anything generated for it
  is a prompt and a quality bar, and belongs with the rest of the quality work.
- **The layout** on the tablet and the phone, including the checks already under way: WebP pictures
  and `<audio>` playback on AnkiMobile, and whether it lets a Listen card play by itself.

The outcome is a list of card changes. A new field or card type is a note-type change, which forces a
full sync — so collect them and make them together.

## 2 · How hard a word is

One figure per word, from Anki, shown the same way wherever the word appears.

- **Where.** The four bars already sit on each row of the word list, drawn from stability. The word
  page shows the raw table instead (stability, difficulty, retrievability, reps and lapses); it should
  show the same bars, per sense and for the word, with the table one tap away.
- **From what.** Anki is the only source: loops and stories report nothing about whether a word was
  known. Candidates are FSRS difficulty (the "Hardest" sort already uses it), lapses, and
  retrievability — computed when shown, from stability and the days since the last review, rather
  than read at pull time and left to go stale. Which one, or which blend, is the open question; the
  figure should be the one the "hardest words" choice for loops and stories uses too
  ([`loops-and-stories.md`](loops-and-stories.md) §1).
- **Not scheduled yet** stays distinct from **weak**: a word with no card shows empty bars and says so.

## 3 · Anki is optional

A deployment without Anki should not look like one with a broken Anki.

- **One switch** in Settings ▸ Anki for the whole integration. Today there are two, sending and reading,
  and nothing reads them outside that panel.
- **Off means no bars.** The list and the word page hide the strength bars and the "Hardest" sort
  when Anki is not in use, rather than drawing every word as unscheduled.
- **Any sync server.** The endpoint and its account are set only in the server's environment today
  (`ACERVO_ANKI_SYNC_ENDPOINT`, pointing at the bundled sync server). Settings should take another
  one, with the credential staying on the server like every other.

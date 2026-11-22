# Compose: the next prompt round, from the judge's inventory

**Status:** Not started. The inventory it works from is measured: the compose judge's full run over the
starter corpus (`experiments/compose-judge/`, `runs/full/report.md`, 21 Nov 2026). It is one step of
the research programme in [`article-quality.md`](article-quality.md), which says why a judge from the
composer's own family is read as leads rather than verdicts (§5, self-preference).

## What the inventory says

Gemini 4 Argon judged 10,152 of the 10,177 starter articles with rubric v2 (only severity 2–3 faults,
a closed set of kinds plus its own `new:` names, and a corrected entry).

- **29% of articles have a severity-3 fault**, but nearly all of the spread between languages is
  transcription. Leave out `field.ipa` and `field.reading` and every vocabulary falls between 14% and
  24% (19% overall). ja-JP's 52% and vi-VN's 48% come from those two fields.
- **The judge lists more than it was asked to:** 88% of articles have a listed fault and 93% came back
  corrected. `note.filler` is in 51% of articles, with one severity-3 instance. Ranking by weight
  (severity summed) puts it first by volume, so choose what deserves prompt space by severity-3 counts:
  `field.ipa` 1,042, `note.false` 940, `example.unnatural` 347, `sense.wrong` 347, `field.reading` 197,
  `sense.missing` 195, `example.missing-word` 95.
- **The two composers, within the 16 vocabularies where both composed ≥ 100 articles:**
  3.5 Flash-Lite 32% with a severity-3 fault, 3.1 Flash-Lite 26%. 3.5 has more IPA faults (17.5% vs
  10%; 3.1 often writes no IPA) and more unnatural examples (11% vs 7%). 3.1 has more false notes (15%
  vs 10%) and missing senses (5.9% vs 3.8%). Which model composed a word was not random, so this is a
  lead, not a ranking.
- The judge's own `new:` kinds came to almost nothing (`example.missing` 18, two one-offs): the closed
  set covers the corpus.

## 1. Checks, not prompt lines

A rule can decide these, so they belong in compose's checks (`vet.py`, `capture.md` table), where they
cost the prompt nothing.

- **A Japanese headword with kanji and no hiragana reading.** 187 of 405 ja-JP kanji headwords have
  none. All were 3.1 Flash-Lite's, which wrote romanisations (正しい → "tá da shī") that the revet
  removed as not hiragana. A missing reading should demote. `apply.py` brings the judge's readings into
  the starters.
- **IPA with no tone in a tonal language.** 120 vi-VN and 103 th-TH transcriptions carry no tone mark
  at all. First decide one tone notation (Chao letters or diacritics; the composers mix both) with the
  IPA guide and the shipped IPA font in mind (`ipa-guide.md`, Android glyphs), then require it.
- **`pos: expression` for a one-word headword** (*sin*, *com*, *mas*, 是). 112 `field.pos` faults.

## 2. Prompt lines worth their room

Each is one change to `prompts/acervo_compose.md`, written for Flash-Lite to follow literally.

1. **Notes: one rewrite covers three kinds.** False notes (940 severity-3, 13% of articles), filler
   (51%) and missing notes (11%). The false ones read by hand hold up (about 11 of 14 in es, en, ru,
   fr, it, pt, de):
   - invented contrasts with the learner's language ("unlike Spanish, *snow* is uncountable");
   - Spanish grammar carried into Portuguese and Italian (*ir a* + infinitive, *querer*);
   - phrases that do not exist (*de bonne tôt*);
   - over-broad grammar rules ("the seasons are feminine" in Polish).

   Candidate: replace the notes paragraph with the rubric's list of what a note may say (the
   preposition or case the word takes, an aspect pair, a separable or irregular form, countability,
   the word it is confused with, a false friend, a register warning). Add "never restate a sense, the
   gloss or the gender" and "leave a claim out unless you are sure it is true of this language".
2. **A sense left in a note.** The commonest `sense.missing` pattern: the everyday use sits in a note
   instead of a sense (*aller* + infinitive, *estar* + gerund, *sapere* + infinitive, *pegar o
   ônibus*, *el corazón* for feelings). Candidate: "a use a learner meets every week is a sense, not a
   note". The worst vocabularies here (pt, es, fr) also have the richest dictionary hints, so other
   languages are probably under-counted.
3. **Senses and examples that are not this word.** `sense.wrong` (347 severity-3) and
   `example.missing-word` (95) share three patterns:
   - a compound's meaning given to the plain word (*Gabel* for *Gabelung*, *Kalenderblatt*, 开会 for 会议);
   - another part of speech (an adverb sense in *a tarde*, a noun sense in the verb 站, *book* as a booking);
   - Spanish interference (Portuguese *bolso* as a handbag).

   Candidate: "every sense and every example is this exact word, in this part of speech".

## 3. How each change is measured

`report.json["keys"][kind][vocabulary]` lists the articles that show each kind, so a change is tried
on exactly those.

- Per change: about 60 articles with the fault, across vocabularies, plus about 30 without any fault
  as a regression control. Compose them with the current prompt and with the changed one, on
  3.5 Flash-Lite (the composer going forward), and judge both with rubric v2 online. Pilot 2 cost
  $0.39 for 72 articles, so a change costs a few dollars.
- Read the target kind's rate and the rate of any severity-3 fault. The judge's own noise is large
  (pilot 1: about a third of faults come and go between runs), so compare the two prompts on the same
  articles in the same judge run, and count a change only if it clears that noise.
- `RUN_LIVE_COMPOSE_TESTS=true` after each prompt change, as for any change to the compose prompt.
- Argon's batch price doubles after 30 Nov 2026, and online calls cost the same either side. The
  judge runs on the `contact` profile only.

## 4. IPA: a different instrument first

The 1,042 severity-3 `field.ipa` faults are about stress, vowel length, tone values and glottal stops.
Most are in languages whose phonology the session could not confirm, and some it could check look
doubtful (Turkish *dünya* with a long *a*, Arabic stress conventions). Two models from similar
training data agreeing is not verification. Before any prompt or check change: compare the composers'
IPA with Wiktionary's own (kaikki's `sounds`, where the compiled dictionaries keep it), per language,
and treat the judge's IPA faults only as the list to compare first. The starters run this
comparison before release (`docs/plans/first-use/starter-vocabularies.md` step 5a); what it finds
per language says whether compose should check those languages' IPA too.

## Not worth prompt space

`sense.oversplit` (1,019 faults, 6 severity-3), `shortgloss.mismatch` (34 severity-3),
`sense.marginal` (13), `example.translation` (20) and `example.unnatural` are real but are either
mild or hard to steer with one line. The judge's corrections fix them in the starters (`apply.py`);
in the app they stay as they are.

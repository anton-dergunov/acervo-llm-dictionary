# Starter vocabularies

**Status:** started 15 Nov 2026. The concept list is drafted and waiting for the owner's review
([`starter-concepts.yaml`](starter-concepts.yaml)); nothing is generated yet.

A new user opens an empty Acervo, and every word costs model calls, pictures and recordings before it
is pleasant to study ([`other-users.md`](other-users.md), "Starting with words already there"). A few
**demo vocabularies**, ready to import with their pictures, recordings, stories and loops, let
someone try the app the day they install it. They are demos first, and useful second: a learner
should be able to study one for real.

## What decides the shape

**Pictures are shared, voices are per language, text is cheap.** A picture shows a meaning, not a
sentence ([`../../features/sense-images.md`](../../features/sense-images.md) §01), so one picture
serves that meaning in every language. A recording is per target language. Text costs least.

**The concept list is the shared core.** A concept is one meaning, labelled in English. Where
languages cut a meaning differently, the concepts are cut finer (`fish-animal` / `fish-food` for
Spanish *pez* / *pescado*; `know-fact` / `know-person` for *saber* / *conocer*). A word in any
language then has senses, each matched to a concept or to none. One with a match takes the concept's
picture; one without gets its own picture, or none.

**The target language is the master.** A vocabulary "Spanish for English speakers" is made once, in
Spanish. "Spanish for Russian speakers" is the same vocabulary with its definitions, glosses and notes
translated: the same words and senses, with no new compose. Recordings are made for the target
language only. Anything in the support language is spoken on demand. Loops are the exception: a loop
is audio, so it ships rendered.

**A2 is the core level, with a little B1.** A2 is "survival plus everyday life", where a shared
picture works in every language. The few B1 abstract words show what the pictures do for an
abstraction (sense-images §01, the *venom* example). Above A2, vocabulary diverges between
languages, so a B1 set is per language and shares fewer pictures.

## What the research found (15 Nov 2026)

There is little hard data; here is what it supports.

- **Demand by language.** English is by far the most learned language (the top language in most
  countries in Duolingo's 2025 report). Spanish, French, Japanese, German, Korean and Italian follow,
  with Japanese and Korean rising. Sources:
  [Duolingo language report summary](https://duolingoguides.com/duolingo-language-report/),
  [second-place languages by country](https://www.voronoiapp.com/society/Whats-The-Most-Studied-Language-in-2026-9064).
- **What learners download is a core list with audio.** The most-voted Anki language decks are
  frequency lists, often with native audio and sometimes pictures: Japanese Core 2k/6k, a 5,000-word
  French deck, a German A1–B1 deck, and TTMIK's First 500 Korean Words with pictures
  ([snapshot of AnkiWeb votes](https://www.mindomax.com/anki-for-language-learning),
  [Japanese decks](https://cotoacademy.com/best-japanese-anki-decks-easy-ways-to-remember-japanese)).
  Fluent Forever's 625-word picture list is the nearest precedent to this one: picturable base words,
  sold as premade picture decks. Learners say a premade deck "saves a bunch of time", though many
  prefer making their own cards
  ([r/FluentForever](https://red.bismuth.it/r/FluentForever/comments/fx5bmw/has_anyone_used_the_premade_speakada_french_625)).
  That is Acervo's case exactly: a starter list to begin with, then your own words.
- **Self-hosted precedent.** Lute ships sample stories in more than 50 languages so the app can be
  tried at once ([Lute manual](https://luteorg.github.io/lute-manual/print.html)).
- **Level.** No source gives a distribution of learners by CEFR level. App learners mostly sit at
  A1–B1, and B1–B2 learners report a resource gap and move to native material, which is where
  Acervo's capture of words met in reading and listening fits. So A2 serves the most people, and a
  B1 set shows the product at its best.
- **Spanish variety.** No survey exists. Guides agree that Americans mostly learn Latin American
  Spanish and Europeans Castilian
  ([MosaLingua](https://www.mosalingua.com/en/which-spanish-should-i-learn/),
  [StoryLearning](https://storylearning.com/which-spanish-dialect-should-i-learn/)). Most of Acervo's
  likely early users read English and come from GitHub, so Latin American (Mexico) goes first.
  Castilian is cheap to add, because the pictures are shared.
- **The interface is English only.** An A2 English learner can browse words glossed in their own
  language but reads the menus in English. Localising the interface is outside this plan.

## The vocabularies

| Wave | Learn | For speakers of | Level | Variety | Who checks it |
| --- | --- | --- | --- | --- | --- |
| 1 | Spanish | English | A2 | Latin American (Mexico) | the owner |
| 1 | English | Spanish, Russian | A2 | US | the owner |
| 1 | Russian | English | A2 | — | the owner |
| 1 | Chinese (Mandarin, simplified) | English | A1, about 150 words | mainland | machine-checked; the owner tries it as a learner |
| 2 | German | English | A2 | Germany | machine-checked; **the owner's own test as a learner** |
| 2 | French, Italian, Japanese, Korean | English | A2 | France, Italy, Japan, Seoul | machine-checked |
| 2 | Portuguese | English | A2 | Brazil | machine-checked |
| 2 | Spanish | English | A2 | Castilian (Spain) | the owner |
| 3 | Spanish, English | as wave 1 | B1, about 250 words, own concepts | as wave 1 | the owner |

- **Definitions** are written in the support language at A2 and in the target language at B1.
- **Chinese** takes about 150 of the A1 concepts, the most concrete, chosen after the concept review.
  Korean and Japanese wait on [`../languages/cjk.md`](../languages/cjk.md) for what does not yet work
  in them (Rare needs MeCab).
- **German** is the owner's own test as a learner: they know very little German, which is exactly
  what an A2 set is for. French or Italian at B1 would make a second test, since they know more of
  those.
- **Wave 2 doubles as the audit** in [`../languages/language-support.md`](../languages/language-support.md)
  §1: building a vocabulary in a language shows what in Acervo does not work in it.

## What each vocabulary carries

- **Words:** the concept list's words in that language, A2, filed under the list's topics.
- **Pictures:** one per concept, shared. A language's own senses with no concept get pictures in wave
  order while credits last.
- **Recordings:** clear voices for every headword, definition and example in the target language.
  These come free under WaveNet's 4M characters a month. A vocabulary is about 250k characters.
- **Stories:** the same ten in every language. Each is written once in English at A2 from shared
  concepts, briefed and drawn once (about 50 pictures), then translated into each target language and
  narrated with the clear voice. It does not have to be how the app makes a story; it has to read
  well.
- **Loops:** ten per target language, made in the app from shared concepts with the clear voice.
  Directed voices are used only if credits remain at the end.
- **Not carried:** spoken clips from the corpus (other people's audio), and anything from the owner's
  own vocabulary or standing rules.

## Budget

The **$280 is trial credit** on the `digest` Google Cloud project: free money, used or lost, which
lasts roughly until mid-February 2027 but could end sooner. So spend it early rather than late.
Without credits, the owner would spend around $30 at most, and would drop directed voices.

**Do not ask Google for a higher quota, or contact Google about these credits at all.** They are
trial credits on a reduced tier, and a request risks a review that takes them away. Throughput is
whatever the default quota gives: about one picture a minute, so the shared core is a day of drawing.

| Item | Pictures | Cost at ~$0.034 |
| --- | ---: | ---: |
| Shared concepts (521 drafted, 497 with a picture) | ~500 | ~$17 |
| Ten shared stories | ~50 | ~$2 |
| Wave 1 languages' own senses | ~4 × 500 | up to ~$70 |
| Wave 2 languages' own senses, if credits remain | | the rest |

Text goes through the Gemini free tier (500 calls a day on each of two models), so compose costs
about a day per language. Claude does the work that needs judgement: the concept list, matching
senses to concepts, the review.

## Order of work

1. ~~**Concept list.**~~ Drafted: [`starter-concepts.yaml`](starter-concepts.yaml), 521 concepts in 16
   topics (337 A1, 152 A2, 32 B1). The owner reviews it on a review page (link in the session that
   made it, and in Claude's project memory). Marks, notes and missing words are stored in the page's
   database: collections `verdicts` (one document per concept id: `verdict` drop/unsure/keep and
   `comment`), `topics` (`missing`, one word per line) and `notes/general` (`text`). **Next session
   starts here:** read them with the artifact data tool, apply them to the YAML, and say what changed.
   After this, the concepts do not change.
2. **Pilot pictures.** Thirty concepts drawn from their concept cards with `src/acervo/images/` called
   directly, so pictures depend on no vocabulary. The review is the existing review sheet
   (`scripts/generate_images.py sheet`). For a shared picture, the sheet also rejects any picture
   with lettering, which the brief prompt otherwise allows.
3. **The shared pictures,** then the ten stories, written, briefed and drawn.
4. **Compose wave 1**, in parallel with drawing, on a dedicated starter account per support language.
   That account has picture drawing switched off, no standing rules and no "About you", and the
   vocabulary's level and variety set. Then match each sense to a concept (one call per word), and
   draft the §0 rubric of [`../quality/article-quality.md`](../quality/article-quality.md) for the
   owner to approve.
5. **Check and review.** The deterministic checks
   ([`../../features/capture.md`](../../features/capture.md), "Compose's checks";
   [`../quality/mandarin-ipa.md`](../quality/mandarin-ipa.md),
   [`../quality/dictionary-checks.md`](../quality/dictionary-checks.md)) run over the composed
   words, Claude reviews against the rubric and corrects, and the owner spot-checks about 20 words each
   in Spanish, English and Russian. **Keep all three layers**: the raw model output, Claude's
   corrections as diffs, and the owner's corrections. Together they are the labelled dataset for
   §1 of `article-quality.md`, with the same concepts across eight or more languages. Claude must not
   later judge its own corrections (`article-quality.md` §5).
6. **Each language's own pictures**, in wave order.
7. **Stories and loops in bundles** (below). Then import each vocabulary into a fresh account as the
   end-to-end test.
8. **Support-language variants:** translate definitions, glosses and notes.
9. **Wave 2**, one or two languages a day; then wave 3.

## What the app needs

- **Bundles that carry stories and loops**, with their pictures and audio
  ([`../../features/export.md`](../../features/export.md) lists what a bundle holds; today it holds
  neither). This is product work, not a converter, and is useful beyond starters: it is how a story
  or loop moves between servers.
- **A laptop builder** next to `scripts/generate_images.py`. It draws concept pictures, places them
  into exported bundles for the matched senses (import already restores a bundle's pictures through
  the attach route, sense-images "The import puts the pictures back"), translates support-language
  fields, and writes the dataset layers. It is a tool, not part of the shipped app.
- **A way to install a starter** from the first-run guide
  ([`first-run-guide.md`](first-run-guide.md)). Until then, Settings ▸ Data ▸ Import is enough.

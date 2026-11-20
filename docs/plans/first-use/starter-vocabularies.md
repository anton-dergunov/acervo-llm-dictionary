# Starter vocabularies

**Status:** the concept list ([`starter-concepts.yaml`](starter-concepts.yaml), 521 concepts in 16
topics) was accepted unchanged on 20 Nov 2026. The builder (`scripts/starter/build.py`) is written;
next is the owner's daily runs, starting with the word lists.

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

Twenty, built from the whole concept list at A2. Each is for English speakers, with definitions,
glosses and notes in English, except English, which is for Spanish speakers. Other support languages
come later, as translations (step 8).

| Learn | Variety (`region`) | What building it tests in Acervo |
| --- | --- | --- |
| Spanish | Mexico (MX) | the baseline the owner can check |
| Spanish | Spain (ES) | a variety pair with Mexico: *coche* / *carro*, *vosotros* |
| English | US (US) | the reversed direction: definitions in Spanish |
| French | France (FR) | gender, liaison, nasal vowels in IPA |
| German | Germany (DE) | three genders, cases, capitalised nouns; the owner's own test as a learner |
| Italian | Italy (IT) | double consonants, gender |
| Portuguese | Brazil (BR) | nasal vowels; close to Spanish, so Spanish must not leak in |
| Russian | — | stress, aspect pairs, cases; the owner can check it |
| Mandarin, simplified | mainland (CN) | tones and Pinyin; no spaces between words |
| Japanese | Tokyo (JP) | furigana, segmentation, Rare refused until MeCab ([`../languages/cjk.md`](../languages/cjk.md)) |
| Korean | Seoul (KR) | pronunciation that differs from spelling; MeCab |
| Arabic | Modern Standard (none) | right-to-left in every view; vowels unwritten; root morphology |
| Hindi | standard (IN) | Devanagari conjuncts in fonts; gender, postpositions |
| Turkish | Istanbul (TR) | stacked suffixes for search; the dotless ı / İ in case conversion |
| Vietnamese | Hanoi (VN) | tones as stacked accents; Unicode normalisation; spaces between syllables, not words |
| Indonesian | — (ID) | the simple case: no inflection, reduplication (*anak-anak*) |
| Polish | — (PL) | seven cases, a Slavic language in Latin script |
| Dutch | Netherlands (NL) | close to German and English, so mix-ups show; *de* / *het* |
| Greek | — (GR) | its own alphabet, written stress, final ς |
| Thai | — (TH) | no spaces between words at all; five tones; vowels above and below |

- **Standard Arabic**, not Egyptian: courses teach it first, everything written is in it, and a
  dictionary can check it. The variety is a preference, so notes can still name the Egyptian word.
  An Egyptian set could follow as a variety pair.
- **`region` is a country**, so it cannot say Hanoi or Standard Arabic; the word lists are told the
  variety in words. Check which variety the Vietnamese voices speak.
- **Who checks it:** the owner checks Spanish, English and Russian. The others are machine-checked,
  labelled so, and ship only once the audit in [`../languages/language-support.md`](../languages/language-support.md)
  §1 passes for them. Building them is that audit.

## What each vocabulary carries

- **Words:** about 450–520 per language. A concept may need two words (Japanese 着る and 履く for
  *wear*) and one word may serve two concepts (Russian рука, *arm* and *hand*). Each word is filed
  under its concepts' topics.
- **Senses matched to concepts**, so a matched sense takes the concept's shared picture.
- **Recordings**, made by the server's enrich after import, with clear voices for every headword,
  definition and example in the target language. They come free under WaveNet's 4M characters a month.
- **Pictures**, as separate steps: shared ones first, then possibly a language's own senses.
- **Not carried:** spoken clips from the corpus (other people's audio), and anything from the owner's
  own vocabulary or standing rules. Stories and loops come later (step 9).

## Budget

Text costs nothing: about 11,000 calls (≈10,400 composes, 320 word-list and 320 match calls) on the
free key's two Flash-Lite models, about 1,000 a day, so roughly 11 days of daily runs.

More free keys (one per Google account, each its own project, so each with its own daily allowance and
8-a-minute meter) shorten that. `build.py run --keys FILE` reads a dotenv file of `GEMINI_API_KEY_<n>`
lines and asks at most three keys at once (`--parallel-keys`), in file order; the last key is a
fallback, used only when the others are spent (`--no-fallback` leaves it out). `--wait` sleeps until
Google's reset at midnight in California and carries on, so one run can be left for days. Three keys
is about 3,000 calls a day, so roughly four days.

The **$280 is trial credit** on the `digest` Google Cloud project: free money, used or lost, which
lasts roughly until mid-February 2027 but could end sooner. So spend it early rather than late.
**Do not ask Google for a higher quota, or contact Google about these credits at all.** They are
trial credits on a reduced tier, and a request risks a review that takes them away. Throughput is
whatever the default quota gives: about one picture a minute.

| Item | Cost |
| --- | ---: |
| Shared concept pictures (497 of the 521 have one), at ~$0.034 | ~$17 |
| A judge on Gemini Pro, if Claude is not used, at ~$0.01 a word | up to ~$100 |
| Pictures for senses with no concept | decided once counted (step 4) |
| Ten shared stories, later | ~$2 |

## Order of work

1. ~~**Concept list.**~~ Accepted unchanged on 20 Nov 2026.
2. **Word lists.** `build.py run` picks each vocabulary's word(s) per concept, one call per topic
   per vocabulary, and merges them into `data/starter/<id>/words.json`. Claude reviews all twenty
   in a session and the owner checks Spanish, English and Russian. Corrections go straight into
   `words.json`, then `build.py review <id>`; a vocabulary is composed only after that.
3. **Compose**, by the same daily runs: one call per word. The builder asks exactly what compose
   asks and judges it with compose's own checks (`compose_parts`, [`../../features/capture.md`](../../features/capture.md),
   "Compose's checks"); resolve is skipped because the word list gives headword, lemma and part of
   speech, and the concept's meaning goes in as the learner's note. One or two vocabularies a day.
4. **Match senses to concepts**, by the same runs once a vocabulary is composed: one call per topic.
   `build.py status` counts the senses with no concept and the concepts no sense covers. **The owner
   then decides** whether to draw pictures for the unmatched senses.
5. **Judge and correct.** The checks already ran at compose. Then a judge from another family than
   the composer flags words against fixed rubric items: wrong gloss, wrong gender, unnatural
   example, above the level, a sense that misses its concept. It gives no score (in
   `experiments/compose-lesson-line/` a judge marked identical pairs different half the time). It is
   Claude on the subscription or Gemini Pro on credits, whichever is available, and is calibrated on
   Spanish, English and Russian against about 50 owner-labelled words each. Drafting the rubric is
   §0 of [`../quality/article-quality.md`](../quality/article-quality.md). **Keep all three layers**:
   the raw model output (the builder's compose files), the corrections as diffs, and the owner's
   corrections. Together they are the labelled dataset for §1 of `article-quality.md`, with the same
   concepts across twenty vocabularies. Whoever corrects does not judge the corrections (§5).
6. **Pictures**, alongside steps 3–5: a pilot of thirty concepts drawn from their concept cards with
   `src/acervo/images/` called directly, reviewed on the existing sheet
   (`scripts/generate_images.py sheet`), which also rejects any shared picture with lettering; then
   the shared ~500.
7. **Bundles and import.** A bundle writer turns the drafts into `acervo-export/1` bundles
   ([`../../features/export.md`](../../features/export.md)). Each is imported into a starter
   account per support language (picture drawing off, no standing rules, no "About you"), where
   enrich makes the recordings. The shared pictures are then placed on the matched senses. Import
   re-mints ids, so a match is found again by headword and definition. Importing into a fresh
   account is the end-to-end test.
8. **Support-language variants:** translate definitions, glosses and notes. The translation sees the
   target word and its sense, never the English alone: *conocer* glossed *know* would become
   Russian знать, which is wrong.
9. **Later:** stories and loops, once bundles carry them; B1 sets per language.

## What the app needs

- **Bundles that carry stories and loops**, with their pictures and audio
  ([`../../features/export.md`](../../features/export.md) lists what a bundle holds; today it holds
  neither). This is product work, not a converter, and is useful beyond starters: it is how a story
  or loop moves between servers.
- **The laptop builder**, `scripts/starter/`: word lists, compose and matching today; drawing concept
  pictures, writing bundles and placing pictures to come. It is a tool, not part of the shipped app.
- **A part of speech for conjunctions and prepositions.** The app's list has none, so *but* and
  *with* are filed as `expression`.
- **A way to install a starter** from the first-run guide
  ([`first-run-guide.md`](first-run-guide.md)). Until then, Settings ▸ Data ▸ Import is enough.

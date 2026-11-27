# Starter vocabularies

**Status:** all twenty vocabularies are composed, judged and corrected (steps 1–5, all but 5a and 5b), their 497 shared
pictures are chosen (step 6), and each is written as a bundle (step 7, [`vocabularies/`](../../../vocabularies/README.md)).
Next: a preview pre-release and the owner's testing accounts; then 5a and 5b before the final
release; then the in-app install ("What the app needs").

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
- **Recordings**, made once in the starter account with clear voices for every headword and example in
  the target language, and carried in the bundle (step 9); an import never records anything. They come
  free under WaveNet's 4M characters a month.
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
| The Argon judge and corrector, pilots included (step 5) | $28.92, spent |
| Pictures for senses with no concept | none: ~4,500 senses, ~$150, many abstract or grammatical |
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
4. **Translate, then match senses to concepts**, by the same runs once a vocabulary is composed.
   First, every definition compose's check doubts for its language is written again in English
   (Spanish for English), seeing the word, its glosses and its other senses; the compose file keeps
   what it replaced. Then one match call per topic.
   `build.py status` counts the senses with no concept and the concepts no sense covers. Senses with
   no concept get no picture: only the 497 shared pictures are drawn, which reach 95% of the words
   (`experiments/compose-judge/README.md`, "Full run").
   When compose's checks change, `build.py revet` applies them to what is already composed: their
   coercions land in the drafts, and a word whose reply they now refuse is set aside with its topic's
   match file, to be composed and matched again by the next run. Run on 21 Nov 2026 after
   `experiments/compose-audit/`: 85 words set aside.
5. **Judge and correct.** ~~Done 21 Nov 2026~~ ([`experiments/compose-judge/`](../../../experiments/compose-judge/README.md)):
   Gemini 4 Argon listed each article's serious faults (a closed set of kinds, no score) and returned
   it corrected. 9,478 corrections replaced their drafts. The 22 left over were corrected by hand in
   a session: 17 the check refused over one slip each, and 5 never judged. Each compose file keeps the
   draft it replaced and the faults. **Keep all three layers**: the raw model output (the builder's
   compose files), the corrections as diffs, and the owner's corrections. Together they are the
   labelled dataset for §1 of [`../quality/article-quality.md`](../quality/article-quality.md), with
   the same concepts across twenty vocabularies.
   Argon is the composer's own family, and whoever corrects does not judge the corrections
   (`article-quality.md` §5). So two checks come **before release**:
   - **a. The Wiktionary pass, mechanical and free.** Compare every starter word's IPA and gender
     with Wiktionary, using compose's own dictionary checks (`dictionary_check.ipa_verdict`, the
     phone error rate; `gender_verdict`). Run them over the served dictionaries and the ten compiled
     for the judge only (`data/dictionaries/judge/`: tr, pl, el, nl, ko, th, ar, hi, vi, id). Compose
     never checked those ten, and they hold the worst transcriptions (vi-VN 43% of articles with an
     IPA fault, tr-TR 25%, ar 18%, th-TH 17%). First count disagreements per language and read a
     sample, to learn where the check's false alarms are (variety, broad vs narrow transcription,
     tone notation). Then take Wiktionary's transcription where the two clearly disagree and
     Wiktionary has one for the vocabulary's variety, and require tone in vi and th. Wiktionary is
     CC BY-SA: a starter that carries its transcriptions says so. The Japanese readings the
     corrections filled in (187 words) are compared with the dictionary's kana the same way; that
     comparison is new, since `reading_verdict` reads only Pinyin.
     This settles the 877 articles whose only severity-3 claim is IPA.
   - **b. A second judge from another family** (Claude), on the severity-3 claims only: about 2,100
     corrected articles, 2,567 claims, most in ja-JP (269). It sees the original, the correction and
     each claim, and answers per claim: true, and fixed rightly; or not true, so the original part
     stands; or fixed wrongly, with the right text. Its answers are applied like the session's own
     (`apply.py`, a run of its own), and what it rejects is a measure of Argon's error rate.
6. **Pictures**, alongside steps 3–5: all 497 shared pictures in one overnight run, reviewed concept
   by concept on a tablet page that also catches lettering, and drawn again where marked.
   `experiments/starter-pictures/` builds the concept cards: a one-sense English article for the
   app's own brief writer, briefs by Flash-Lite. It draws them with Nano Banana 2.1 in Vertex batch
   jobs on one pinned account, and holds the review page.
7. **The package, bundles and release.** The package is the top-level
   [`vocabularies/`](../../../vocabularies/README.md), tracked, kept apart from the builder's record in
   `data/starter/` (requests, replies, the drafts each correction replaced). Hand fixes still go into
   the builder's files, so the three layers stay separate.
   - **A starter is an `acervo-export/1` bundle**, one per vocabulary
     ([`../../features/export.md`](../../features/export.md)), with no format of its own.
     `web/scripts/starter-bundle.ts` reads each word's final draft and its senses' concepts from
     `data/starter/`, puts the concept's picture on the first sense matched to it (one picture of a
     meaning per word), and writes the bundle with `bundleFiles`, the function export uses. It reads
     every bundle back through `readBundle` and refuses one that does not parse.
   - **What is tracked:** the shared pictures (`vocabularies/pictures/`, with `pictures.json`: brief,
     style, template checksum, the models that wrote the brief and drew it) and each vocabulary's
     bundle text, unzipped (`vocabularies/<id>/`, one file per word, readable on GitHub), with
     `placement.json` saying which picture each bundle picture path takes. The pictures are the only
     original content: chosen by hand and drawn without a seed, so they are never treated as a cache.
   - **What is not:** the zips (`vocabularies/out/`, ignored), rebuilt byte for byte from the tracked
     files and attached to a GitHub release (`vocabularies-YYYY.MM.N`, a series apart from the app's).
     Each is ~125 MB, nearly all pictures; `vocabularies/catalogue.json` names the release, each zip's
     size and SHA-256. A pre-release comes first; the final release follows steps 5a and 5b and a
     chosen licence for the text and pictures, stated in `vocabularies/README.md`. Google does not claim
     what Gemini generates, and machine-made content may carry no copyright at all, so the licence
     mostly says what is allowed: CC BY 4.0 is the likely choice, or CC BY-SA if Wiktionary
     transcriptions are folded in (5a).
   - **Placement is by bundle path**: `media/<lang>/<slug>-<n>.webp` is the nth sense of
     `<lang>/<slug>.yaml`, as for any exported picture, so nothing is matched again after import.
   - **Testing accounts.** `scripts/starter/test_accounts.sh [--fresh]` creates
     `starters@account.example.com` (every starter but es-ES) and `starters-es@account.example.com` (es-ES,
     so it is not imported into the first's Spanish) on the deployed server, and installs the zips with
     the app's own import, run headless (`web/scripts/install-bundle.ts`). Each account is set first to
     run nothing else by itself (picture drawing, Anki and the nightly steps off); the import itself
     queues nothing in any account. Importing into these accounts is the end-to-end test, and the first
     of them is where the recordings, stories and loops are made later (step 9). They are an interim:
     an account now keeps several vocabularies of a language, so
     [`../several-vocabularies.md`](../several-vocabularies.md) moves the starters into the owner's own
     account and retires them.
8. **Support-language variants:** translate definitions, glosses and notes. The translation sees the
   target word and its sense, never the English alone: *conocer* glossed *know* would become
   Russian знать, which is wrong.
9. **Later:** recordings, three stories and three loops per vocabulary, once bundles carry stories and
   loops. The release zip then becomes an export of the starter account, with recordings of the
   target language only (headwords and examples). Audio lives in the release, never in Git: it is per
   language (twenty copies, where a picture is one), regenerable, and ~20–50 MB a vocabulary, so
   ~0.4–1 GB for twenty. Measured rates give per vocabulary: headwords ~3 MB (5.7 KB each), examples
   +17–34 MB (34 KB each), three stories ~7 MB, three loops ~13 MB (4½ min of MP3 at 128 kbps each),
   so ~150–180 MB in all. B1 sets per language follow.

## What the app needs

- **Bundles that carry stories and loops**, with their pictures and audio
  ([`../../features/export.md`](../../features/export.md) lists what a bundle holds; today it holds
  neither). This is product work, not a converter, and is useful beyond starters: it is how a story
  or loop moves between servers.
- **The laptop tools**, not part of the shipped app: the builder `scripts/starter/` (word lists,
  compose, translation, matching, and a follow-up match for senses added after a topic was matched),
  the bundle writer and the headless installer in `web/scripts/`.
- **A part of speech for conjunctions and prepositions.** The app's list has none, so *but* and
  *with* are filed as `expression`.
- **A way to install a starter from inside the app**, built with the first-run guide
  ([`first-run-guide.md`](first-run-guide.md), step 2) and the standalone app. Until then a person
  downloads a zip from the release and uses Settings ▸ Data ▸ Import. The design, so it adds a source
  and not a second import:
  - The browser cannot fetch a release asset (github.com's redirect carries no CORS header), so the
    server does. `GET /starters` answers the shipped `vocabularies/catalogue.json` and which zips it
    holds; a `fetch-starter` job downloads the zip the catalogue names (the catalogue is the
    allow-list), checks its SHA-256 and keeps it under `<data>/starters/` as a cache, with its failure
    sentence in `admin log`; `GET /api/acervo/starters/{file}` serves it (bearer, `FileResponse`).
  - The import panel lists the catalogue as a second source, "Start from a ready vocabulary". Choosing
    one fetches through the server, then shows the same confirmation — as a new vocabulary, or added
    to one of the owner's of its language — and runs the same `importThroughServer`. An import spends nothing: no job, no model call,
    and its senses without a picture stay without one ([`../../features/export.md`](../../features/export.md), "Import").
  - Pictures then travel server → device → server (~125 MB each way). If that is slow on a tablet,
    the picture route can take "from starter X, path P" instead of the bytes: the same route.

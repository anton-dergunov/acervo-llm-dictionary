# Similar projects

**As of:** September 2026. A quick survey rather than a market study: one pass over what is findable,
enough to say where Acervo overlaps with other work, where it does not, and what that implies.

No project found does what Acervo does as a whole. Most of its parts, taken one at a time, exist
somewhere else, and some of those places are crowded. The difference is the combination: one
personal, multilingual, sense-level graph that every kind of enrichment hangs off.

## The landscape

| Category | Examples | What they do better | What Acervo does that they do not |
|---|---|---|---|
| **Spaced repetition with LLM-written entries** | Jiaci (open source; LLM entries shared by all users, scheduled with ts-fsrs), Mochi, Anki add-ons | They own the review loop: scheduling and study *are* the product. | Senses as first-class records, provenance modelled rather than flagged, several languages in one graph. Scheduling is delegated to Anki rather than competed with. |
| **Sentence mining from media** | Migaku, LingQ, Language Reactor, Trancy, VocabSieve | Capture at the point of contact — inside a streaming service, a reader, a video — with little setup and a polished surface. | The clip corpus runs the other way: they find words inside media you chose; Acervo finds real speech for a word you already hold, with a model checking it is *this* sense. Nothing comparable was found. |
| **AI stories from your word list** | Storyling, LexiTale, Memfy, Miao AI, MeloLingua | Commercial polish, many languages, catalogues. **This is a crowded category.** | Stories drawn from the learner's own graph, narrated passage by passage with a direction each, with marks in both languages. A difference in quality, not in kind. |
| **Music** | Lingotify (real songs plus spaced repetition), Soundverse (generic generated songs) | Real songs carry culture that a generated track does not. | LexiBeat loops: built from the learner's own words, timed per word, with a translation never shown before it has been spoken. Nothing close was found. |
| **LLM vocabulary knowledge graphs** | DIY-MKG (EMNLP 2025 demo track): a personal graph grown by LLM-suggested related words, plus LLM-generated quizzes | The nearest research analogue to discovery by expansion. | Far deeper as a system — a durable store, sync, enrichment, media. DIY-MKG has almost no community around it, so the idea has a paper and the product space is still open. |
| **Visual lexicon explorers** | Visual Thesaurus, Visuwords, word2vec-graph, word-galaxy | Beautiful exploration of a *general* lexicon. | None of these is personal or multilingual. Acervo's meaning map is both: one learner's senses, per language (see below). |

## Open-source tools considered as a base

Before building, the closest open-source tools were read as candidate foundations. None was adopted:
each treats the word list as scaffolding for its one output, so adopting it means adopting its centre
of gravity. The distinctive part — a synced, offline-capable, personally curated store of words as the
system of record, with pluggable consumers — is precisely what none of them is.

| Project | What it is | Why not | Worth stealing |
|---|---|---|---|
| [VocabSieve](https://github.com/FreeLanguageTools/vocabsieve) | Sentence mining → Anki. Local StarDict/MDX/DSL dictionaries, lemmatization, frequency lists, EPUB reader. | Desktop Qt. No sync, no phone, no LLM, no server. Anki is the only output. | **Its dictionary-format parsers** — the best prior art you'll find. |
| [Lute v3](https://github.com/LuteOrg/lute-v3) | Self-hosted Flask. Learn by reading; per-word status New → Known; multi-word and parent terms. | Reading-centric — vocabulary is a byproduct of imported texts, not a curated list you own. Online dictionaries only. | Its multi-word term handling and status model. |
| [anki-llm](https://github.com/raine/anki-llm) | CLI/TUI for bulk LLM processing of Anki notes; a JSON-oriented AnkiConnect wrapper. | A tool *for* Anki, not a vocabulary store. No durable core. | Its AnkiConnect usage as a reference. |
| [playphrase](https://github.com/kelciour/playphrase) | Self-hosted subtitle search that plays the matching video fragment. | Local media files, not embedded YouTube. | Proof the clip feature is a solved shape. |
| [Obsidian → Anki](https://github.com/ObsidianToAnki/Obsidian_to_Anki) family | Markdown → Anki, some LLM-assisted. | One-directional pipes from notes to cards. | Nothing. |

## How Acervo differs

- **Personal and sense-level.** One owner, several languages at different levels, and senses as
  separate records rather than a word with a list of meanings. Provenance is part of the model: an
  attestation says where a word was met, a generated example names its model, a clip names its voice.
- **Breadth of enrichment on one graph.** Per-sense pictures briefed together per word, retrieved
  real speech, directed text-to-speech, loops, stories and offline dictionaries all read the same
  records, so an enrichment added later works on every word already held.
- **Decisions are measured.** Constrained decoding, audio encoding, caption quality and clip
  selection were each settled by an experiment with numbers, and the write-ups are in
  [`experiments/`](../../experiments/README.md). That is rare in hobby projects and uncommon in
  commercial ones.
- **Offline-first and self-hosted.** Every read works without a network, and the data is the
  learner's own.
- **Discovery from interest, not ignorance.** The published work on vocabulary recommendation —
  Riiid's Pedagogical Word Recommendation — predicts what a learner does not know, pooled across a
  population. Acervo's sibling research repository, `interest-aligned-vocabulary-recommendation`,
  asks what one learner would *want* to learn next, from their vocabulary alone.

## Where it is weak, and what is planned

### The learning loop is not closed

Acervo builds the entry and hands study to Anki, so it cannot yet say whether anything it does helps
a word stick — the thing every competitor sells.

**Planned.** The Anki connection is to be wired up in both directions: cards go out to Anki, and
review statistics come back into Acervo. Anki is not going to be reimplemented. What Anki cannot do
is where Acervo adds activities of its own: loops and stories already exist, and how often a word
is heard — in a loop, in a story, as a played pronunciation — is exposure the application can
count. Those counts join the review statistics as a familiarity signal, used later to rank words
and to bring forward the less familiar ones. More activities are to come, and they are still being
thought through.

### Capture is text-first

The immersion tools meet the learner inside what they are already reading or watching. Acervo
waits for a scrap of text to be brought to it.

**Planned, in two directions.**

- **More ways in.** Capture from a photo — tap a word in a picture of a page and it is added — is
  built ([`photo-capture.md`](../features/photo-capture.md)). Capture from speech may follow,
  as a secondary goal.
- **Immersion inside Acervo itself.** Generated stories and examples already contain words the
  learner does not know. Tapping one should show a short translation and, if the word looks worth
  having, add it without leaving the application. That makes Acervo's own generated material a
  source of new words, which none of the story apps above treat as a capture surface.

### The vocabulary is seen one way at a time

The vocabulary is a list, sortable and grouped into topics, and a meaning map of one language's senses
([`../features/meaning-map.md`](../features/meaning-map.md)). Neither shows how words relate across
languages, to what the learner knows well and badly, or to what is missing.

**Planned, as ideas rather than specifications**: some forty views — a concept grid across languages,
word families, clines, a character network, a strength map and more — under one idea, that **every view
with slots is a recommender**, drawing a proposed word where a place is empty. The map's version of that
is its ghosts. The catalogue is [`../plans/word-discovery.md`](../plans/word-discovery.md).

### Heavy to maintain, and hard for anyone else to run

A NAS, Docker, several model providers with their own credentials, and two companion services.
Acceptable for one owner; a ceiling on its value as a public project.

**Planned.**

- **A standalone macOS application**: download, open, use, with the data kept on the machine and no
  server at all. This is a real design change rather than packaging — today every write is a round
  trip to the server, by design — and it has its own plan,
  [`../plans/first-use/standalone-mac-app.md`](../plans/first-use/standalone-mac-app.md).
- **A simpler self-hosted path** for anyone who wants sync across devices.
- **A hosted service** with downloadable desktop and mobile applications is a possibility if the
  project succeeds, and is not planned now: it needs a server somewhere and the resources to run it.

Only macOS is in scope for the standalone application. Other platforms may come later and are not a
priority.

### Evaluated on one person

Every measurement so far is n-of-1. That is honest, and it limits what can be claimed.

**Planned.** Opening Acervo to other learners, including languages the owner is not learning.

## Sources

- Spaced repetition: [awesome-fsrs](https://github.com/open-spaced-repetition/awesome-fsrs),
  [awesome-fsrs site](https://open-spaced-repetition.github.io/awesome-fsrs/),
  [open-source Anki alternatives](https://alternativeto.net/software/anki/?license=opensource)
- Sentence mining: [Migaku vs Language Reactor](https://www.langpanda.com/compare/migaku-vs-language-reactor),
  [Language Reactor alternatives](https://www.trancy.org/blog/7-best-language-reactor-alternatives-compared-2026-3609d2252005811db7f7d41131756428),
  [Migaku alternatives](https://wordy.info/blog/migaku-alternatives),
  [LingQ alternatives](https://lexirise.app/blog/article/free-lingq-alternative),
  [VocabSieve](https://github.com/FreeLanguageTools/vocabsieve)
- Stories: [Storyling](https://www.storyling.ai/), [LexiTale](https://www.lexitale.ai/en),
  [Memfy](https://apps.apple.com/us/app/memfy/id6756895423), [Miao AI](https://miaoai.app/),
  [MeloLingua](https://melolingua.com/ai-story-language-app)
- Music: [Lingotify](https://www.lingotify.app/),
  [Soundverse on songs for language learning](https://www.soundverse.ai/blog/article/how-to-make-ai-songs-for-language-learning-content-0232)
- Knowledge graphs: [DIY-MKG](https://github.com/kenantang/DIY-MKG)
- Visual explorers: [Visual Thesaurus](https://www.visualthesaurus.com/),
  [word2vec-graph](https://github.com/anvaka/word2vec-graph),
  [word-galaxy](https://github.com/lusilva/word-galaxy),
  [Visual Thesaurus alternatives](https://alternativeto.net/software/visual-thesaurus)
- Recommendation: Shin & Park, *Pedagogical Word Recommendation*, [arXiv:2112.13808](https://arxiv.org/abs/2112.13808)

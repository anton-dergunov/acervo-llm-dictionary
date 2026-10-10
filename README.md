# Acervo

Acervo is a personal dictionary of the words you chose to learn. Paste a word, or the sentence you met it in: the entry is written for you, with a picture for each meaning, a recording, and clips of native speakers saying it. You read it before it is saved. From the same words it makes audio loops, illustrated stories and a map of what you know. It is self-hosted, and every device keeps the whole vocabulary, so it reads offline.

![A dictionary of the words you chose, written and illustrated for you. The application in a macOS window, open on the Spanish verb "sonar" over the list of words: its pronunciation, its first definition, the translations "to ring, to sound, to go off", a picture of a ringing red telephone, the sentence it was met in with its translation, and a box to ask about the entry. Beside it, the word's three meanings, each with its emoji and a picture carrying the style it was drawn in: to ring, in claymation; to ring a bell, as a manga panel; to seem, in retro-futurism. Everything in an entry is generated, so the dictionary can go from any language to any other, at your level; the author's are Spanish to English, English to Russian and Chinese to English. Entries follow your own standing instructions, and you review, edit, or ask for changes in the chat. From the same words: recordings, clips of native speech, audio loops, illustrated stories, a map of meanings, words from a photo, Anki cards, offline on every device. Measured in 13 experiments in this repository, 7 in Spoken Usage Retrieval, which finds the clips, and 2 in LexiBeat, which makes the loops.](assets/pictures/word.png)

No model is trained here. The work is in deciding where a model is trusted and where it is checked, and each of those decisions was measured: [`docs/ml.md`](docs/ml.md) is the tour, and [`experiments/`](experiments/README.md) holds the apparatus and the results.

## Getting a word in

Paste a sentence and the word is picked out of it; a word you already hold is recognised, not added twice. The entry is drafted in two model calls, one to decide what the text is about and one to write it, and nothing is stored until you save; you can ask for changes in a chat under the draft. The same pipeline walks a file of notes into an inbox, one entry at a time. See [capture](docs/features/capture.md).

![Paste the sentence; read the entry before it is saved. Three steps. One: the Add view with the sentence "Ayer trasnoché para terminar el informe y hoy no puedo con mi alma"; the phrase is worked out for you and the sentence is kept as your own example. Two: the generated entry for the idiom "no poder con el alma", with pronunciation, a definition in Spanish and translations; pictures, clips and recordings are added in the background after you save. Three: a request typed under the draft, "Add an example about Monday mornings", answered with a proposed edit to review.](assets/pictures/capture.png)

Or photograph a page and tap a word. An OCR engine says where the words are, a segmentation model says where the sentences end, and a fast language model says what the tapped word means in that sentence. See [photo capture](docs/features/photo-capture.md).

![Photograph a page, tap a word, see what it means there. A phone showing a photographed book page with the word "otorgó" outlined and its sentence highlighted, and below it "otorgar: awarded, granted" with the whole sentence as it will be kept. How it works: take a photo; every word becomes tappable because the OCR engine returns each word with its outline; tap any word and its sentence is found; the meaning in that sentence appears in about a second, and Add keeps the word, the sentence and the photo. In the entry the sentence then carries the photo it came from, drawn here for the same page. Each part was chosen by experiment, with thresholds set before measuring, on 13 photos and screenshots of Spanish text with 59 taps checked by hand. Reading the page: Cloud Vision, chosen, put the right word under the tap 98% of the time and was tappable in 1.6 to 1.9 seconds; RapidOCR, a local model, 80% (68% on book photos) and 7.5 seconds. Finding the sentence: the SaT segmentation model, chosen, 98%; punctuation rules 69 to 74%. The meaning of the tap: a fast language model, chosen, in 1.0 second, right 85% exactly and 98% nearly; a more accurate one took 4.4 seconds.](assets/pictures/photo.png)

## What is made around a word

**A picture for each meaning.** A language model sees every sense of the word at once and writes a brief for each, in a style it picks for each; an image model then draws them. See [sense images](docs/features/sense-images.md).

![One word, three meanings, three pictures that look nothing alike. "la trampa" branching into its three meanings, each with its emoji and a picture carrying its style: a trap, as a watercolour of a woman crawling into a wicker fish trap; a trick, as a film-noir office with a ledger left as bait; cheating, as a comic-book card game. Below, the brief a language model wrote for the first. How a picture is made: the meanings of the word with a definition and an example each; a language model writes a brief for each, one concrete scene that shows this meaning and not the others, exaggerated so it sticks, in one of 23 styles it picks, which you can change before redrawing; an image model draws each brief. The brief prompt was tuned by hand over eight rounds and 2,285 pictures: each round the author kept or rejected every picture and wrote why, and the prompt was changed. Round one rejected 7 of 14 and the last 0 of 50. Rules that came out of it: show the meaning itself, never hint at it; exaggerate by adding to the subject; keep the cast small; what separates two meanings must be in the frame.](assets/pictures/pictures.png)

**Native speakers saying it.** You add the YouTube channels you like to watch. [Spoken Usage Retrieval](https://github.com/anton-dergunov/spoken-usage-retrieval), a separate project, indexes their captions; the videos stay on YouTube. One model call per word decides which passages really use this meaning and translates them; a word with no good clip gets none. See [spoken clips](docs/features/spoken-clips.md).

![Hear the word from a native speaker, at the moment it is said. An example in the entry for "atropellar" that carries a clip, "Tengo miedo de que me atropelle un coche", and the player it opens, three seconds into playing a street interview, with the words said so far marked and the translation "I'm afraid that a car might run me over" below. How it works: Spoken Usage Retrieval, a separate repository, reads the captions of your YouTube channels and indexes every word by its form and its dictionary form, while the videos stay on YouTube; when a word is saved the index returns candidate passages and one model call keeps those that use this meaning and translates them, where keeping none is a valid answer; the clip plays from YouTube at that second, the words light up as they are said, and words are aligned with the translation. Measured, old prompt against a rewritten one over 10 passages, 4 target languages, 3 models and 343 calls: badly cut-off translations went from 8 to 0 and fully covered ones from 81% to 91%, McNemar p = 0.004. A starter list of channels is curated for Spanish; any channel can be added in Settings.](assets/pictures/clips.png)

**A conversation about the entry.** A question is answered in prose, and an edit arrives as a proposal you review. The change marks come from comparing the entry before and after, never from the model's own account of what it changed. See [article chat](docs/features/article-chat.md).

![Ask about an entry; the answer can be a change you review. On the left the entry for "sonar" with a question about "me suena", the answer, a proposal to add an example with a song, and the box for the next question. On the right the entry with the new example marked in place and the buttons Discard and Save changes. The chat is on every device and under a draft before it is saved.](assets/pictures/chat.png)

## Loops and stories

A loop says each of the words you picked, leaves a beat to recall it, and then gives the translation, over music generated for it. There are several kinds, from a plain drill to a radio lesson and a story. It is made by [LexiBeat](https://github.com/anton-dergunov/lexibeat), a separate generator, from recordings Acervo directs. See [loops](docs/features/loops.md).

![Your words over music, with the answer held back until it is spoken. A phone playing a radio-lesson loop over the list of loops: "ir de cabeza" and its translation "be swamped" have been said, its example "Voy de cabeza con los impuestos este mes" is being said, and that translation is still a bar. Kinds of loop: classic drill, alternating, radio lesson, story, and two more. How it is made: you choose the words; the voice is expressive on purpose, and a word said three times is three recordings, each with its own direction from a language model; the music is generated new for every loop as a rhythmic background, and one you like can be kept and reused. Chosen by ear, in LexiBeat: 687 clips scored 1 to 5 on a tablet, covering drill rhythms, examples, stories, commentary, voices mixing languages and ways to say a hard word; stories and commentary scored highest, and because asking a voice to speak fast gives about 1.3 times the speed while a fancier direction is as often slower, speed is set by stretching the audio.](assets/pictures/loop.png)

A story is written around a handful of words, in a kind you pick or leave to chance, in four parts, each with a picture and a translation, and read aloud with a direction for the voice written for each passage. Any word in it can be tapped to look it up. See [stories](docs/features/stories.md).

![A short illustrated story written around a handful of your words. The first part of "La leyenda de la laguna": a picture of a toad by a stream, the text with two of the owner's words marked, and its translation with the same two words marked. Beside it the story's four pictures, numbered. You choose the words, one of 13 kinds of story from funny to mystery to myth, and the picture style, or leave them to chance. Each part is read aloud with a direction a language model wrote for each passage, here "Mythical and grand, with a resonant, storytelling tone". Measured: with the first picture of each returning character given as a reference, a blind side-by-side comparison of 12 pairs preferred the referenced set 9 times, with 3 ties and none against; and in 25 of 25 calls the passages cut for narration joined back into the exact text.](assets/pictures/story.png)

## The map

Every meaning is embedded from its definition and translations, laid out in two dimensions, and grouped into regions that a model names. See [the meaning map](docs/features/meaning-map.md).

![Every meaning you hold, laid out by what it means. The map zoomed in on "la deuda", joined to "el préstamo", "cobrar", "garpar", "la cuenta" and "el fondo", with a card giving its definition; and the whole map of 1,457 meanings with its named regions, such as "Dinero y justicia" and "Emociones y conflicto". How it is made: each meaning, not each word, is embedded with a multilingual encoder; UMAP lays the meanings out in two dimensions; they are grouped into about 8 regions and 30 neighbourhoods, which a language model names. You learn where things are on a map, so adding a word should not move the rest: with a fixed seed it still moved, and starting from the last layout and aligning to it cut the median move after one edit from 140 to 37 units.](assets/pictures/map.png)

## One server, every device

Acervo is self-hosted: one machine of your own keeps the dictionary and does the generating, and nothing is hosted for you. Each device holds a complete copy, so everything opens with no connection; a save is one request to the server and fails visibly without it. See [sync](docs/architecture/sync.md) and [the server](docs/architecture/server.md).

![One server of your own, and the whole dictionary on every device. A diagram. Your server, one machine at home, runs Acervo (one Python service and one SQLite file holding the dictionary, its pictures and recordings, and the background jobs) beside Spoken Usage Retrieval, LexiBeat and an Anki sync server. It calls model providers, in an order you set, and clips play from YouTube. A phone, a tablet and a Mac each hold a complete copy: changes are pulled as they happen, and a save is one request, online only. With no connection you can still search, read, listen, and play loops and stories you have opened before. A thousand words take a few megabytes; pictures and recordings are fetched when first shown, then kept.](assets/pictures/sync.png)

The interface is one web app: open it in a browser, install it on Android and iOS, or use the native macOS window, which also lives in the menu bar.

![The whole vocabulary on every device, readable with no connection. The word "sonar" on a phone and on a tablet, as cards to swipe, and in a desktop window as a page. It opens in a browser or installs as a web app on Android and iOS, and on macOS it is a native window that also lives in the menu bar.](assets/pictures/devices.png)

## Anki

Cards are built from your entries and kept up to date for you: a minute after you stop editing, the changed words are sent to an Anki sync server running beside Acervo, and your phone or tablet picks them up the next time Anki syncs. Every hour the review state comes back, so the word list can show which words are hardest. Content goes one way and statistics the other. See [Anki](docs/features/anki.md).

![Your words as Anki cards, made and kept up to date for you. The front and the back of one card for "sonar": the word in its sentence, then "to ring", the definition, the sentence with its translation, and the picture. Beside them, how the cards travel: Acervo sends cards to Anki's own sync server on your machine, Anki on your phone or tablet syncs with it as usual, and reviews come back every hour. Below, the Anki page in Settings with the switch "Send changes to Anki". Scheduling stays with Anki, and no desktop needs to be running.](assets/pictures/anki.png)

## How an entry is made

Two model calls write the text while you wait. A save then queues one job in the same transaction as the word, and the job finds clips, draws pictures and makes recordings on the server, with the app open or closed, through a chain of model providers that falls through to the next on a rate limit, an error or an unusable answer. Every generated record names the model that answered, and one id joins the logs. See [jobs](docs/architecture/jobs.md), [models](docs/architecture/models.md) and [observability](docs/architecture/observability.md).

![From a pasted word to a finished entry, step by step. While you wait, in the app: a word, a sentence or a photo; a language model resolves which word and language it is and whether you already hold it; a language model composes the meanings, definitions, translations, examples and notes; you review and save. After Save, on your server, one background job per word, in three branches. Clips: search the caption index, then a language model selects and translates the passages that use this meaning. Pictures: a language model writes a brief for each meaning, then an image model draws each. Recordings: a speech model records the word, its definitions and its sentences, kept as Opus, and the Anki cards are updated. Below, the Activity page in Settings, which shows what the server is doing, and the same job in the server's log with every line under one id. A loop and a story are made the same way, and each model is one of a chain of providers, so when one is rate limited or fails the next answers.](assets/pictures/pipeline.png)

## How it was measured

Each prompt, model and pipeline step was tested on real words before it was kept. The write-ups, with their scripts and results, are in [`experiments/`](experiments/README.md); the two projects Acervo is built on carry their own, in [Spoken Usage Retrieval](https://github.com/anton-dergunov/spoken-usage-retrieval/blob/main/experiments/index.md) and [LexiBeat](https://github.com/anton-dergunov/lexibeat/tree/main/experiments). What is still open, including the quality programme for entries, stories and clip selection, is in [`docs/plans/`](docs/plans/README.md).

![Design choices were measured. Eight experiments, each as question, measurement and decision. Which style does the model pick from a list: offered in file order it kept picking the first row, so the list is rotated for each word and every style says what it suits. Is the whole passage of a clip translated: with a rewritten prompt, cut-off translations fell from 8 to 0 and fully covered ones rose from 81% to 91% over 343 calls. Do earlier pictures as references keep a story character the same: preferred blind in 9 of 12, with 3 ties. Do two more fields in the prompt make the rest of the entry thinner: no, over 315 calls. Does the map stay put when a word is added: aligning to the previous layout cut the median move from 140 to 37 units. From Spoken Usage Retrieval: searching by dictionary form takes the verb "estar" from 24 found uses to 499; and aligning captions written by people to the audio cut word timing error from 333 ms to 59 ms, while automatic captions needed none. From LexiBeat: of 687 clips scored by ear, a hard word said syllable by syllable came out wrong half the time, and the whole word said slowly was right for 14 of 15.](assets/pictures/experiments.png)

The pictures on this page are captures of the application on a real vocabulary; [`assets/pictures/`](assets/pictures/README.md) has their sources and the script that retakes them.

## Core model

The canonical graph separates eight records with different lifetimes:

- `vocabulary` — a language being studied, and the languages to translate it into;
- `topic` — an editable grouping label with an optional symbolic icon;
- `lexeme` — the word or phrase being learned;
- `sense` — one ordered meaning with target-language definition and multilingual glosses;
- `attestation` — the verbatim context in which the learner encountered it;
- `example` — a curated or generated sentence with explicit language and provenance;
- `imagePrompt` — a regenerable prompt associated with a lexeme or sense;
- `studyState` — statistics reported by an external learning system.

Every record uses a client-generated 15-character ID, belongs to one account, and carries
replication-ready edit metadata. Markdown vocabulary files and extended-article JSON are not
application storage formats.

See [the design documents](docs/README.md) for the product decisions,
[the server design](docs/architecture/server.md) for what runs on the always-on machine, and
[the application guide](docs/operations/deployment.md) for deployment details.

## Development

Requirements are Python 3.12, Node.js 20+, Docker for server integration tests, and macOS 14 plus
Xcode/XcodeGen for the native host.

```bash
uv pip install -r requirements/dev.txt
uv pip install -e .
npm install --prefix web

pytest
npm --prefix web run test
npm --prefix web run build
npm run test:pwa
npm run test:mac
```

Run the application stack locally with:

```bash
./deploy.sh --local --configure-credentials
```

Self-registration is disabled and there is no superuser. Accounts are made one at a time, with the
password read from the terminal:

```bash
./deploy.sh --create-account
```

The API exposes password login and token refresh; there is no generic CRUD surface over the
vocabulary at all — the graph routes are the only way in or out.

## Disposable demonstration data

Once an account exists, insert owner-scoped demonstration entries with:

```bash
docker exec -i acervo-server-1 \
  python -m acervo.admin seed --owner-email learner@account.example.com
```

It writes through the service layer rather than over HTTP, so it needs no password, and it is
idempotent: a second run skips what the account already holds. The sample graph includes thirteen
editable starter topics plus fifteen lexemes covering multilingual glosses, phrases, attestations,
generated examples, prompts, study statistics, and a Chinese reading.

## Components

- `web/src/domain.ts` — canonical TypeScript records and runtime validation.
- `web/src/localDatabase.ts` — IndexedDB replica and atomic storage operations.
- `web/src/repository.ts` — offline CRUD, tombstones, and pending markers.
- `src/acervo/` — the server: the canonical schema, the graph routes, capture, the dictionary
  routes, auth and the static surfaces. See [the server design](docs/architecture/server.md).
- `deploy/acervo/server/` — the image it ships in.
- `src/acervo/client.py` — the one HTTP client against the API; every job and script goes through it.
- `src/acervo/dictionaries/` — the external-dictionary compiler.
- `src/acervo/images/` — the sense-image pipeline: a brief writer and a renderer. Stands alone
  on `src/acervo/models/`, so a route and a batch sweep share it.
- `src/acervo/jobs/images/` — the unattended half: the run directory, the sweep, the import.
- `src/acervo/consumers/anki/` — headless Anki consumer infrastructure.
- `experiments/` — experiments, spikes and benchmark tooling, outside the distribution and never imported by the service.
- `macos/` — native host for the shared web interface.

Deployment is designed for shared hosts and uses dedicated configurable listeners. It never assumes
ownership of ports 80/443 or unrelated proxy, Tailscale, firewall, or Docker configuration. On a
tailnet, Acervo is published as its own Tailscale service, which gives it a hostname and a 443 of
its own without touching the host's — what Android requires to install it alongside another
self-hosted app.

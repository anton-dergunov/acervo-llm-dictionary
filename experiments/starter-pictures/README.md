# The starter vocabularies' shared concept pictures

## Question

The twenty starter vocabularies share 521 concepts (`docs/plans/first-use/starter-concepts.yaml`),
and 497 of them get one picture that every vocabulary shows with the senses matched to it (the
other 24 are `pic: none`). How should a picture be drawn from a concept rather than from a word, and
on which route can all 497 be drawn overnight? The plan is
`docs/plans/first-use/starter-vocabularies.md`, steps 6 and 7.

## Method

**The concept card** (`cards.py`). A concept becomes a one-sense English article, so the app's own
brief writer (`acervo.images.brief.BriefWriter`), template (`prompts/acervo_image_brief.md`) and style
table (`config/image-styles.yaml`) take it unchanged. Both are settled (`docs/features/sense-images.md`),
and nothing is added to them.
- The headword is the word en-US matched to the concept, or the concept's id without its suffix
  (`fish-animal` → *fish*).
- The definition and short gloss are the concept's English `sense`.
- The notes hold the concept's `note` and the definitions that three vocabularies matched to it. These
  pin the meaning: es-ES, de-DE and ru first, since they cut meanings differently from English and
  from each other (*conocer*, *kennen*, *знать* for `know-person`).
- The glosses are those three headwords.
- It has **no example sentences**. The first cards carried en-US's matched sense's examples. The
  writer did what the app asks of it and drew the sentence: "My wife loves to read books in the
  evening" became a woman reading alone, and "He is my only son" became a framed portrait. Without
  examples, the same eight hard concepts were drawn as the meaning itself: a wedding band on both
  hands, a family resemblance, a shoemaker recognising an old friend. A picture shown under twenty
  vocabularies has to carry the meaning on its own, so the 23 briefs written with examples were
  discarded.

**The briefs** (`run.py briefs`). Flash-Lite (`gemini-3.5-flash-lite`, then `gemini-3.1-flash-lite`)
writes them on the free key in the root `.env` (`GEMINI_API_KEY`), at most 8 calls a minute.
- The prompt drawn is `compose(brief, style)`. Its frame forbids every kind of lettering, since a
  shared picture is shown under twenty languages.
- Each brief is kept in `results/briefs/<concept>.json`: the card, the request, the style, the
  situation, the brief, the composed prompt, the prompt version and the call's usage.

**The drawing** (`run.py draw`, `vertex.py`). This is the route the character pictures settled on
(`experiments/character-pictures/README.md`, "The full run"): Nano Banana 2.1
(`gemini-nano-banana-2.1`) in Vertex batch jobs.
- One job is in flight at a time, of at most 250 pictures. Jobs submitted together shared one lane
  there and drew no faster.
- About one picture a minute, at about $0.0244 a picture: half the list price, plus the thinking
  tokens.
- Each picture is drawn from its prompt alone: square, 1K, no seed. It is encoded by
  `encode_master` (1024² WebP).
- The batch code is copied from that experiment's `batch.py`, and its fixes are kept. Rows the
  24-hour limit never reached are asked for again, not counted as refusals. The state is saved before
  a job is created. Each check prints the job's progress and says `STALLED?` after 90 minutes without
  a new picture.

**The account.** Vertex is called only on the Google account, project and gcloud configuration
(`acervo-contact`) that the gitignored `.env` beside `run.py` pins. `.env.example` shows its keys.
`gcp.py`, copied from the compose judge, checks all of these before anything is sent:
- no shell variable may redirect gcloud or a client;
- the ADC file's account (asked of Google) and its quota project;
- the gcloud configuration's account and project.

Files go only to `gs://<project>-starter-pictures`. A job created outside the project's number is
cancelled at once and the run stops. The cap is `--cap` (default $25) over everything this
experiment has spent, holding $0.04 for each picture in flight.

**The review** (`review.py`). One concept a screen, on the tablet:
- the sense, the note, the matched words, the style and the brief;
- the latest take of the picture;
- **✓ Good** and **↻ Redraw**, with a note on what is wrong.

Labels go to `results/labels.json`, each naming the take it judged.

## Running it

From the repository root:

```bash
.venv/bin/python experiments/starter-pictures/run.py briefs     # about an hour; reruns skip what is written
.venv/bin/python experiments/starter-pictures/run.py check      # the account, and what a draw costs
caffeinate -i .venv/bin/python experiments/starter-pictures/run.py draw 2>&1 | tee -a experiments/starter-pictures/out/draw.log
.venv/bin/python experiments/starter-pictures/run.py status     # from another tab, any time
.venv/bin/python experiments/starter-pictures/review.py --host "$(tailscale ip -4)"
```

- **`draw`** checks every 5 minutes (`--poll`), collects a finished job, and submits the next only
  once none is in flight. It stops by itself when every concept with a brief has a picture.
  - `--dry-run` says how many pictures it would submit, and stops.
  - Ctrl-C at any time, then run the same command again. A job in flight keeps running at Google,
    and `out/batches.json` keeps the rerun from submitting it twice.
  - `--limit N` draws at most N pictures; `--concepts a,b` draws only those concepts.
- **A refusal** (an answer with no picture) is logged in `results/draws.jsonl`, and the next run
  asks again. A concept refused twice is skipped unless named with `--concepts`.
- **`STOPPED:`** means an expired login, a refused setting or an account that cannot pay. Pictures
  already finished are kept. After `gcloud auth application-default login` as the pinned account,
  the same command carries on.
- **Redrawing:** `run.py draw --redraw` draws the next take of every concept labelled `redraw`
  (after its brief is revised from the note, if it needs revising). The new take shows on the page,
  unlabelled. A concept rejected again can carry several ideas in its brief file's `variants`
  (each with its own brief, style and prompt); `--redraw` then draws one take per idea, and the page
  shows the new takes as thumbnails to pick from.

Files:
- `results/`, tracked: the briefs, `draws.jsonl` (one line per take: brief, style, prompt version,
  model, tokens, cost, or the error) and `labels.json`.
- `out/`, ignored: the masters, `out/pictures/<concept>/<take>.webp`, until the chosen ones move
  into `vocabularies/pictures/`; the batch state, which names the project's number; and the logs.

## Results

**Smoke test, 22 Nov 2026.** One job of three pictures (`mother`, `know-person`, `wait`) on the
pinned account. It was queued for a minute and drew all three in four minutes, refusing none, at
$0.0202–0.0219 a picture (790–1,333 thinking tokens). It proves the account guard, the bucket, the
model on this project and the harvest. Those briefs still carried example sentences, so the
pictures are set aside in `out/smoke/`, and their log lines in `results/smoke.jsonl` still count
toward the cap. The full run draws these three concepts again from their new briefs.

The guard refused, before sending anything, a shell whose `CLOUDSDK_CORE_ACCOUNT`,
`GOOGLE_APPLICATION_CREDENTIALS` or `CLOUDSDK_ACTIVE_CONFIG_NAME` named anything else.

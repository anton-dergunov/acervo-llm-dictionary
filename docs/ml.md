# The machine learning in Acervo

Acervo is a vocabulary store first, and almost every model in it is a hosted one reached through a
chain the owner orders. What makes it interesting as an ML system is not a model it trains — it trains
none — but the decisions about **where a model is trusted, where it is checked, and how that was
measured**. This page is a tour of those decisions; each is argued in full in the document it links to,
and the experiments behind them are in [`../experiments/`](../experiments/README.md).

---

## Calling models at all

- **No constrained decoding, anywhere.** Structured output is asked for with JSON *mode* and a shape
  stated in the prompt, then checked by the caller's own parser. A JSON Schema made the clip selector
  draft inside string values — translations grew from 61 characters to over a thousand, three calls in
  four timed out — and bought an alignment task no accuracy at any size before being rejected outright
  above ~100 tokens. A schema guarantees validity, never correctness, and its failures pass every check
  a parser can make. ([`architecture/models.md`](architecture/models.md))
- **An unusable answer falls through to the next model.** A model that cannot hold a shape has revealed
  a fact about itself, so the caller raises `unusable` inside the chain and the next pair is asked —
  quality-triggered routing with no second call and no vote. Compose does not yet do this for its own
  field checks. ([`architecture/models.md`](architecture/models.md), [`plans/quality/article-quality.md`](plans/quality/article-quality.md))
- **Hedging for latency.** A caller with a person waiting races the next pair when the first is silent
  past a delay set from measured healthy answers; the first usable answer wins.
- **The model is named by the record.** Every generated record carries the model that *answered*, which
  is what makes regeneration safe years later.

## Writing entries

- **Two calls, resolve then compose**, because deciding *what* a scrap of text is about — which word,
  which language, which sentences are the learner's — is a different job from writing the article, and
  answering the first is what lets duplicates and unknown languages stop before anything is generated.
  ([`features/capture.md`](features/capture.md))
- **Grounding on a dictionary entry** demotes the model from knowledge source to selector and formatter,
  and recovers the senses a model drops when asked cold. Whether it makes better articles is unmeasured,
  and the owner's impression is that it does not — so it is an experiment waiting to run.
  ([`plans/quality/grounding-spike.md`](plans/quality/grounding-spike.md))
- **Adding fields to a prompt without thinning the rest** was measured before trusting it: ten substance
  metrics each moved less than their own run-to-run variance across 315 calls.
  ([`features/loops.md`](features/loops.md) §2.8)

## Pictures

- **Brief per word, draw per sense.** One text call sees every sense of a word, so it can make the two
  senses of *venom* deliberately look nothing alike; then one image call per sense.
- **The writer chooses the style from the whole table, rotated per word**, because offered in file order
  it reads the first row as the default — position bias, found in review.
- **The abstract sense is externalised as a physical presence** in the scene: bitterness as a corrosive
  vapour, not a woman looking angry. Eight review rounds took the reject rate from 7 in 14 to 0 in 50
  with the image model unchanged. ([`features/sense-images.md`](features/sense-images.md))
- **Continuity in a story is chosen by who and where**: a later picture is conditioned on the *first*
  picture of each returning character and the *last* of its place, at most two, and none when nothing
  recurs. Blind comparison won 8–0 in drawn styles, lost 4–0 in the photoreal one, and won 7–0 with 3
  ties there once the reference prompt was reordered. ([`features/stories.md`](features/stories.md))

## Spoken clips

- **Retrieval by the corpus, judgement by the model.** The corpus does IR over millions of segments;
  Acervo spends one frontier call per word on whether a fragment is really an instance of *this* sense.
- **Refusing is the default.** A thin corpus must produce articles with no clips, never bad clips, and a
  hallucinated id is dropped and counted rather than failing the word.
- **The model chooses and never rewrites**, so the passage-boundary research on the corpus side keeps
  measuring something. ([`features/spoken-clips.md`](features/spoken-clips.md))
- **Translating the whole passage**, demanded in the prompt, took severe truncation from 8 to 0
  (McNemar p = 0.004). Whether code should also refuse an incomplete translation waits on data across
  enough scripts to set a threshold honestly. ([`plans/quality/translation-completeness-check.md`](plans/quality/translation-completeness-check.md))

## Voices

- **Encoding chosen blind.** The provider's 32 kbps MP3 was the one thing a listener picked out every
  time; the master is asked for and encoded as Opus at ~60 kbps, indistinguishable from uncompressed.
- **A reference and a reading are different voices**: one stable voice per language for a headword,
  one that takes a direction for a sentence. ([`features/pronunciation.md`](features/pronunciation.md))
- **Three takes of one line must differ**, so the take cache keys on the repetition index — a director
  note quantises prosody into adjectives, and two takes can carry identical instructions.
  ([`features/loops.md`](features/loops.md) §2.5–§2.6)
- **A model's segmentation is never trusted with the words**: narration passages are tiled back onto the
  original text, so whatever the model changed stays in as an undirected passage.
  ([`features/stories.md`](features/stories.md))

## The meaning map

- **Embed a sense, not a word**, from `headword (pos) — definition — glosses`, with a multilingual
  encoder because every text mixes two languages. Two encoders tied on topic agreement at more than twice
  chance.
- **UMAP with `min_dist` 0.1** gives the map islands; the price is instability, and a fixed seed does not
  pay it — the map came back mirrored. Warm-starting from the previous layout and a Procrustes alignment
  took one edit's median movement from 140 units to 37.
- **Cluster the 2-D layout, not the vectors**, so a region's label sits over its points; Ward rather
  than HDBSCAN, whose noise class would discard the long tail of minor interests.
- **Names by a model, off the drawing path**: deterministic labels read as lists or boilerplate.
  ([`features/meaning-map.md`](features/meaning-map.md))

## Reading a page

- **Geometry from an OCR engine, judgement from a language model.** A multimodal model's boxes are
  approximate and its text can be invented; Cloud Vision's are not, and it hit the tapped word 98% of
  the time where a local engine on the NAS managed 68% on book photos.
- **SaT over rules** for sentence boundaries, because OCR text carries a status bar, a URL and a heading
  that end in no punctuation: 98% of taps against 69–74%.
- **A fast model for the tap**, at 1.0 s median against 4.4 s for a more accurate one — the tap cannot
  afford it. ([`features/photo-capture.md`](features/photo-capture.md))

## Editing with a model

- **The model's output is a set of operations against record ids, and the change marks are computed by
  diffing two drafts, never by reading the operations** — a model's account of its own edit is one more
  thing that can be wrong. The word-level diff uses `Intl.Segmenter`, since a regex makes a Han sentence
  one token. ([`features/article-chat.md`](features/article-chat.md))
- **What a live model does, and the contract that survives it**: a comparison question reliably proposes
  an edit however firmly told not to, so the rule held is "never rewrite what is there unasked", pinned
  by a live test.

## What evaluation taught

- **Pairwise "which is better" cannot resolve small differences** — human or model. Same-arm controls
  could not reliably return "no preference", agreement with a judge was at chance, and the verdict had to
  rest on metrics. A judge must be re-established on each task. ([`plans/quality/story-quality.md`](plans/quality/story-quality.md))
- **Blind comparison where the question is perceptual** — audio encodings, picture references — with
  the arm hidden and position randomised, because reading position alone produced a 14-to-4 lean.
- **Ground truth before quality claims.** A comparison of two prompt arms is blind to a defect both
  share: both wrote the same wrong IPA. The ground-truth harness is the first thing the article-quality
  programme builds. ([`plans/quality/article-quality.md`](plans/quality/article-quality.md))
- **Measure at the largest input the caller produces.** The alignment schema worked at sixty tokens and
  failed at a hundred and five.

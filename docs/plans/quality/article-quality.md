# Article quality · the research programme

**Status:** Open. Part register of defects, part reading list, part experiment backlog. Nothing here
blocks anything, and it is populated as things are found.

`prompts/acervo_compose.md` writes every article Acervo holds, and the parts a learner trusts most —
a transcription, a register, a tone mark — are the parts they are least able to check. Word articles
are the product's central artifact; translations are second. So this is the one place where being
*correct* matters more than being *fast, cheap or tidy*, and the only place in the repository where
that question is open rather than settled.

**It is also deliberately the project's research track.** An engineering fix teaches little and
transfers nowhere. A designed experiment that returns a null result — as
[`compose-lesson-line`](../../../experiments/compose-lesson-line/README.md) did — is a reusable output:
an instrument, a measured claim, and a finding that survives the codebase it came from. That framing
decides how this file is written: every section below names a question, an instrument and what a
negative answer would still be worth.

Two consequences worth stating up front. **This file is wide on purpose** — it collects everything
known rather than the shortlist worth doing first, because the shortlist changes and the survey does
not. And **§9's reading list is the most portable thing in it**: fourteen papers that say something
specific about validating generated text, each with what it implies here.

---

## §0 · What a good article is — the gap that blocks everything else

**No criteria are written down anywhere in this repository.** Not in the design document, not in the
prompt, not in the validators. Every measurement in §1 onwards needs them, and their absence is why
the compose experiment could only ask *did this change anything* rather than *is this any good*.

A candidate rubric, assembled from the literature and from Acervo's own stated rules:

**Definitions** — the four criteria from *Towards Automated Lexicography* ([2601.01842](https://arxiv.org/abs/2601.01842)),
which are aimed at learner's dictionaries and therefore at exactly this artifact:

| criterion | question |
| --- | --- |
| truthfulness | is the definition true of the word |
| coverage | does it cover the sense, not a fragment of it |
| sense specificity | does it distinguish this sense from the word's others |
| guideline compliance | does it obey the dictionary's own house rules |

**Examples** — GDEX: typicality, informativeness, intelligibility, used against LLM output in
[2410.03182](https://arxiv.org/abs/2410.03182).

**Fields with a single right answer** — `ipa`, `reading`, `gender`, `pos`, `register`, `dialect`,
`lemma`. These need ground truth, not judgement.

**Acervo's own rules, which are already written but nowhere checked** — gloss-language completeness
and the language each gloss is in, the notes language, the three-to-five sense target, `domain` shape
(one or two words, lower case, distinct between senses), one emoji that depicts the *word* rather
than its topic.

**The distinction that organises everything below:** a field with a checkable answer wants ground
truth and a string comparison; a field that is a matter of judgement wants a rubric and a rater, with
all the unreliability that implies. Conflating them is what produced the null result in
`compose-lesson-line`, where a preference instrument was pointed at fields that mostly have right
answers.

---

## §1 · The ground-truth harness — the first thing to build

A tracked word list with **expected values per field**, scored per (provider, model) pair. Field-level
accuracy against truth, rather than preference between two articles.

### How the truth gets made, and why that is the weak point

Three sources, in descending order of trustworthiness:

1. **Dictionary-derived** for `ipa`, `reading` and `gender` — see §3. Mechanical, reproducible, and
   the only tier that does not depend on anybody's judgement.
2. **Published references** where they exist — a standard dictionary's transcription, a pinyin table.
3. **Model-drafted and hand-curated**: the strongest available model writes a reference article, the
   owner edits it until satisfied, and that becomes the expected value.

Tier 3 is a **weak gold standard and must be labelled as one**. It is a single annotator, working
from a model's draft, which imports that model's biases into the ground truth it is supposed to
judge. [2410.03182](https://arxiv.org/abs/2410.03182) reports *low inter-annotator agreement* on
dictionary example quality specifically — so disagreement about the judgement fields is the expected
result, not a sign the rubric is broken. Two mitigations worth designing in: draft the reference with
a model that is **not** in the evaluation set, and record the curator's edits as data, since what a
human changes about a model's draft is itself a finding about that model.

### Soft matching, not string equality

`/ˈas.ko/` and `/ˈasko/` are both correct — Vertex wrote both across six calls. Exact comparison
would score a right answer wrong, which is worse than not measuring. The instrument wants a
normalisation step (strip syllable separators, stress marks where not contrastive, length marks) and
then a distance with tolerance. [2606.11639](https://arxiv.org/abs/2606.11639) proposes exactly this
for IPA evaluation — a *Soft PER* that tolerates linguistically similar phoneme substitutions
alongside standard phoneme error rate — and that is the shape to copy.

### What transfers from `compose-lesson-line`

Most of the apparatus, which is the argument for building this next rather than later:

- `dataset.py` — a tracked YAML list turned into exactly what the shipped compose call takes.
- The **direct per-pair calls** that bypass `chain.walk`, because a fall-through would attribute one
  model's answer to another.
- The manifest pinning prompt digests, dataset digest, and every pair with its skip reason.
- `--dry-run`, the cost ceiling, the per-row pacing, the parked-pair rule.
- **Repeat-major ordering**, which is what kept the comparison balanced when Cloudflare's allowance
  ran out mid-run.
- `score.py --selftest`, which validates the metric against the failures it exists to catch before
  anything is spent.
- `noise()` — the within-arm variance that turns a raw delta into a readable one.

What changes: scoring compares against **expectations** instead of against the other arm, and there
is one arm rather than two.

### What a negative result would be worth

If every model scores well on every field, the finding is that article quality is not the bottleneck
and the effort belongs elsewhere — which is worth knowing before building §2 through §6. The IPA
defect suggests otherwise, but one word is not a rate.

---

## §2 · What can be checked with no model at all

Acervo already has a check doctrine. Naming it is worth doing, because it is transferable knowledge
independent of this codebase.

### The six shapes of check already in use

| shape | example | where |
| --- | --- | --- |
| **verbatim containment** | a marked span must literally occur in the text it marks — untrimmed, uncased, un-normalised | `draft.py`, `domain/validation.py`, `domain.ts`, `clips/select.py` |
| **closed-set membership** | `pos`, `gender`, `register`, `origin`, `sourceKind` | `SELECT_RULES`, `pick_choice` |
| **grounding an identifier in what the request offered** | sense ids, segment ids, topic names, `fromSentence` indices — never trusted, always intersected with the request | `clips/select.py:parse_reply`, `draft.py:_from_sentence` |
| **referential integrity, including the second hop** | an attestation belonging to the right owner but the *wrong word* must still fail | `validation.py` |
| **co-presence / co-absence** | `translation` ↔ `translationLang`; a brief needs `styleId` + `promptVersion`; `imageModelId` requires `imageRef` | `validation.py` |
| **anti-degeneracy on prose** | field-name leakage into a string, a generous length ceiling, exact-copy-instead-of-translation | `clips/select.py` only |

### The four dispositions

Equally reusable, and the part most codebases get wrong by having only one:

- **Coerce** where a fallback exists — `pick_choice`, `emotion_of`'s truncate-at-a-word-boundary.
- **Drop the field, keep the record** where the field is decoration — `matchedForm`, an unknown topic.
- **Drop and count** where it signals a prompt bug worth surfacing — a hallucinated segment id.
- **Refuse and demote** only where the record would be meaningless — no senses, a Chinese entry with
  no reading, a model that runs fields together.

### The architectural finding: a failed check already routes to a better model

This is the most useful thing in this file.

`clips/select.py` raises its validation failures **from inside the chain callback**:

```python
except ValueError as unusable:
    raise ProviderUnavailable("unusable", …, provider_id=candidate.row.id, model=candidate.model)
```

`chain.walk` treats `unusable` as retryable, so that pair is **passed over and the next one is
asked**. The reasoning is already recorded in `models/errors.py`: *"A model that answers with the
wrong shape has not revealed a mistake in the deployment — it has revealed that this model cannot do
this job, which is exactly what a chain of alternatives is for."*

Applied to `ipa`, this closes the register's issue 1 without a second call, a vote, or a stronger
model: gemini's `/ˈaska/` fails the check, gemini is demoted, and Vertex — correct 6 of 6 — answers.
**The architecture already implements quality-triggered model routing** — and it does so without
touching the locked contract that a record names the model that did the work, because exactly one
model still produces the field.

**But not for compose yet, which is where these fields are written.** Routing works where the
caller parses inside the `ask` callback: `clips/select.py` and `images/brief.py`. Compose goes
through `services/models.llm_json`, which raises `unusable` only when a reply is not JSON and takes
no validation hook; compose's own refusals — no senses, a Chinese entry with no reading, a reply
that is not an object — are raised as `ApiError` after the chain has finished, so they are terminal
and no stronger model is asked. **An in-chain compose check first needs `llm_json` to accept a
validation callback**; with that, the gloss-script check (backlog row 3) is the first check to add
and the template for the IPA one.

### The rule-decidable checks not yet written

Each needs nothing but the reply and the request:

- **gloss script against `glossLangs[0]`** — `llama-3.3-70b` answered in English 28% of the time for
  vocabularies that gloss into Russian first. `score_of`/`script_of` in the experiment's `score.py`
  is already a working implementation.
- `primaryGloss` is a single term — no `;`, `,` or `/`.
- `emotion` is 3–12 words, carries no emoji, and is not identical to one of the article's own example
  emotions.
- `domain` shape, and distinctness between the senses of one word.
- `emoji` is one grapheme cluster, not a run of them.
- `lemma` versus `headword` for languages where the relation is mechanical (`el disfraz` → `disfraz`).
- notes language by script, the same way as glosses.

### Where a check can live, and what each home costs

| home | reach | constraint |
| --- | --- | --- |
| `domain/validation.py`, called from `repository/graph.py` | **every** writer — typed YAML, capture, the headless job, imports, Anki | pure by design, runs inside the SQLite transaction, so no network, no dictionary, no model call — and it is mirrored in `web/src/domain.ts`, so every new refusal is two implementations |
| `services/articles.py:save_article` | articles only | has the vocabulary's configuration, as the `unknown_topic` refusal already uses — but `POST /graph` bypasses it, so an import skips it |
| a chain callback | one field, one call | demotes the model (above); the only home that improves the answer rather than refusing it |
| a job step | anything | may do I/O, so it is the only home for §3 — but it runs after the record is stored |

### The literature that bears on this

[Let Me Speak Freely?](https://arxiv.org/abs/2408.02442) finds format restrictions degrade reasoning,
and stricter constraints degrade it more — independent corroboration of the constrained-decoding
decision already recorded in `AGENTS.md` from this project's own measurements. Note precisely what
that decision forbids: schema-constrained *decoding*. **Post-hoc validation is its complement, not
its contradiction** — the decision exists *because* "a schema guarantees validity, never correctness",
which is an argument for checking the content afterwards.

---

## §3 · Deterministic derivation and dictionary grounding for the countable fields

The fields with right answers mostly have *published* right answers, and Acervo already compiles
them.

### IPA is already in the artifacts

`src/acervo/dictionaries/converters.py:127` reads wiktextract's `sounds[].ipa`, preferring a
slash-delimited transcription:

```python
def _ipa_of(record: dict) -> str | None:
    sounds = record.get("sounds") or []
    for sound in sounds:
        raw = sound.get("ipa")
        if raw and raw.startswith("/"):
            return raw
```

So `kaikki-es-en` and `kaikki-es-es` carry Spanish IPA, `kaikki-ru-*` Russian, `kaikki-en-*` English.
This is the register's "only option that actually closes it", and it is **free, offline, and already
built** — the compiled dictionary is a local file answering byte ranges.

### `reading` has a better source than a model

CC-CEDICT carries numbered pinyin per entry, which is deterministic where a model is not. Note that
`web/src/pinyin.ts` is a **renderer, not a validator**: it converts `ma2 fan5` to `máfan` for
display, and cannot detect `máfán`, which is already accented and passes through untouched. Its own
docstring says it is "deliberately not a transliterator and deliberately not a word segmenter".

### `gender` is available and discarded

Wiktextract carries gender in `head_templates`, and `head_templates` is in `WIKTEXTRACT_DROP`. So the
only mechanical source for `lexemes.gender` is one converter change away — and
`experiments/external-dictionaries/spike.py` already listed `gender` among its draft keys, so this
was noticed and not done. Adding it costs an `Entry` field, a `DictionaryArticle` field and a
converter branch.

### No phonetics tooling exists

Zero hits across the repository for `espeak`, `phonemizer`, `epitran`, `pypinyin` or `g2p`. A
grapheme-to-phoneme route — the classic one, e.g.
[massively multilingual neural G2P](https://arxiv.org/abs/1708.01464) — would be new dependencies and
belongs in an experiment's own environment, never in `requirements/`. Worth comparing against the
dictionary route rather than assuming: a G2P tool covers every word including ones no dictionary
holds, while a dictionary covers only its headwords but carries the *attested* transcription.

### The cheaper alternative the register already names

For a language whose orthography determines its transcription, **deriving or omitting `ipa` beats
asking a model for it.** Spanish is such a language; English is emphatically not. A field that is
mechanically derivable is a field no model should be asked to produce — and the experiment worth
running first is simply how often each model's `ipa` disagrees with the dictionary's, per language.

---

## §4 · Cross-model consensus, cascades, and confidence without logprobs

### What exists, and what does not

**No k-way vote primitive exists.** Two mechanisms re-issue a call and neither compares answers:

- `chain.walk`'s hedging races at most `IN_FLIGHT = 2` pairs and **discards the loser's content by
  design** — `_abandon` lets it finish in the background and `journal.late` records only that it
  answered. First usable answer wins.
- `SHAPE_TRIES = 2` retries a whole chain when every reply was malformed, and its comment shows the
  concept is already understood: *"the only thing a retry can change here is the sample"*.

So the thread-pool machinery for a fan-out is present and the comparison is not. Building one raises
a real design question to record rather than skip: **a voted field has no single author**, which
collides with the locked contract that an entry records the model that did the work.

### Why sampling the same model cannot catch this bug

The sharpest methodological point available from this project's own data.

[SelfCheckGPT](https://arxiv.org/abs/2303.08896) is the black-box hallucination detector for exactly
Acervo's situation — no logprobs from a frontier API — and it rests on one assumption: *if a model
knows something, sampled responses agree; if it is hallucinating, they diverge*. Self-consistency
methods share that assumption.

`/ˈaska/` came back **6 of 6 times**, both arms, all three repeats. A confidently and uniformly wrong
model defeats every sampling-based confidence estimate, and would have been scored as maximally
reliable. This is a clean counterexample worth writing up.

**Cross-model disagreement does catch it** — 2:1 across the three pairs in the run. Which produces a
neat tension with the generation literature:
[Mixture-of-Agents](https://arxiv.org/abs/2406.04692) aggregates several models and
[Self-MoA](https://arxiv.org/abs/2502.00674) then found that repeated sampling from a *single* top
model often beats mixing different ones. Both can be true, because **verification and generation want
opposite things from model diversity**: generation wants the best single distribution, verification
wants independent ones. Acervo can test this directly, since its chain already holds three models
with measurably different failure modes.

### Cascades

[FrugalGPT](https://arxiv.org/abs/2305.05176) names three cost strategies — prompt adaptation, LLM
approximation, LLM cascade. Acervo's provider chain **is** a cascade already, but it escalates on
*failure* (429, 5xx, unusable shape), not on *quality*. §2's checks are precisely what would convert
it into a quality cascade, which is the cheapest version of "just use the frontier model": use the
cheap one, and escalate only the words it demonstrably got wrong.

### Confidence without logprobs

[Can LLMs Express Their Uncertainty?](https://arxiv.org/abs/2306.13063) surveys verbalised
confidence, sampling and aggregation for black-box models, and reports the usual finding that
verbalised confidence is poorly calibrated and overconfident. For this project it is doubly
unpromising: the one error under investigation was produced with no variance at all. Worth recording
as a route considered and set aside **with a reason**, rather than left unexamined.

---

## §5 · Verification and correction by a second model

The idea is to hand a generated article to another model and let it judge or repair. The literature
splits sharply, and the split is the useful part.

### Intrinsic self-correction does not work

[LLMs Cannot Self-Correct Reasoning Yet](https://arxiv.org/abs/2310.01798) (Huang et al., ICLR 2024)
tests *intrinsic* self-correction — a model revising its own answer with no external feedback — and
finds performance sometimes **degrades** after correction. So "ask the model to review its article" is
the version least likely to help.

### Tool-grounded critique does work

[CRITIC](https://arxiv.org/abs/2305.11738) has the model verify its output by *interacting with
tools* — an interpreter, a search engine, a calculator — and revise from what comes back. That is the
shape to build: a correction call fires **only when a deterministic check has already failed**, and
is handed the specific complaint rather than the whole article to admire.

```
check fails: ipa /ˈaska/ ≠ dictionary /ˈasko/
  → "This entry's ipa is wrong. The dictionary says /ˈasko/. Return only a corrected ipa."
  → {"ipa": "/ˈasko/"}
```

### Decontextualised verification answers the conditioning worry

The objection that a verifier's output is "conditioned on the input it receives" has a name and a
remedy. [Chain-of-Verification](https://arxiv.org/abs/2309.11495) drafts, plans verification
questions, **answers them independently so the answers are not biased by the draft**, and only then
revises. For an article that means: ask "what is the IPA of *asco*?" in a fresh context rather than
"is `/ˈaska/` correct?", because the second question carries its own answer.

### Atomic decomposition

[FActScore](https://arxiv.org/abs/2305.14251) breaks a generation into atomic facts and scores the
share supported by a reliable source — and found ChatGPT at 58% on that metric. An article decomposes
naturally: each sense is a claim, each gloss is a claim, each example is a claim about usage. The
per-claim structure is also what makes a *partial* verdict possible, which a whole-article judgement
is not.

### Judge pathologies, to design against and to reproduce

- **Self-preference**: [LLM Evaluators Recognize and Favor Their Own Generations](https://arxiv.org/abs/2404.13076).
- **Why** it happens: [Self-Preference Bias in LLM-as-a-Judge](https://arxiv.org/abs/2410.21819)
  reports judges scoring lower-perplexity text higher regardless of who wrote it — so a judge may be
  measuring *familiarity* rather than correctness, which is a reason to prefer checks with right
  answers wherever one exists.
- **Position bias** — already designed against here by asking both orderings and treating a flip as
  no difference. Measured flip rate: 19%.
- **Low inter-annotator agreement in this exact domain**: [2410.03182](https://arxiv.org/abs/2410.03182)
  again. The κ ≈ −0.10 measured on 18 September is the published expected result, not a broken
  instrument.

### The cost arithmetic, from measured numbers

| | input | output | cost |
| --- | ---: | ---: | ---: |
| compose, `gemini-free/3.5-flash-lite` | ~3,100 tok | ~410 tok | **$0.00215** |
| compose, `vertex/gemini-3.8-flash` | ~3,100 tok | ~480 tok | **$0.0085** |
| verify-and-correct, a checklist and one article | ~900 tok | ~100 tok | **~$0.0005** |

The mechanism is more specific than "input is cheaper than output": of a compose call's **12,347
request characters, 10,600 are the prompt itself**. A verifier needs the finished article and a
checklist, not the compose prompt, so the *instruction* shrinks by an order of magnitude. Generate
cheap and verify strong lands near **$0.004** against **$0.0085** to generate on Vertex throughout —
half the price, keeping the cheap model's 1.8 s median.

### Both experiments are worth running

- **Check-triggered repair**, the CRITIC shape. Likely the right final design.
- **An unconditional review step** on §0's four criteria, despite the weak evidence for it — because
  testing [2310.01798](https://arxiv.org/abs/2310.01798)'s claim against this project's real articles
  is a result either way. If ungrounded review helps here and the paper says it should not, that is
  the more interesting outcome.

---

## §6 · Grounding — shipped, disliked, and unevaluated

Grounding shipped as the user-initiated reference path (`docs/plans/quality/grounding-spike.md` records it):

- `services/capture/coerce.py:reference_of` — `REFERENCE_LIMIT = 8000`, and a docstring that states
  the modelling rule: *"Grounding, and nothing else. It never reaches `resolution.sentences`, so it
  can never become an attestation."*
- `build_user_message` appends the reference block and one of two treatment lines,
  **STAY CLOSE TO THE REFERENCE** or **FILL IN THE GAPS**.
- `prompts/acervo_compose.md` has a whole section governing it.
- Reached from `ExternalArticle.tsx`'s "Add to my words".

**The owner has used it and dislikes the articles it produces.** That is an unmeasured impression and
is recorded here as one — but it is a reason to *evaluate* the implementation, not to close the spike.
The spike is therefore re-scoped: from "should we ground?" to **"what does the grounding we shipped
actually do to an article?"**, which is a better experiment because the implementation already exists
and can be compared against itself switched off.

### What to measure, from the spike's own design

- **Not recall.** The recorded metric is whether the senses *shown* change, and whether the changes
  are improvements.
- **A hard negative check on sense count**, because *sense inflation is the recorded failure mode*:
  "If grounding causes more senses to be shown, that is the failure mode to watch for, not the
  success metric."
- **No regression on simple words** — a source that adds senses to `picar` and clutter to
  `el cuchillo` is one to apply selectively.
- Three arms rather than two: ungrounded, `faithful`, `expand`.

### Why grounding can hurt, in the literature

Directly relevant, and directly adjacent to the owner's professional work on retrieval-augmented
generation:

- Irrelevant and noisy retrieved context degrades accuracy, sometimes sharply; see the
  [RAG survey](https://arxiv.org/abs/2312.10997) for the landscape.
- **Knowledge conflict is worse than noise** — context contradicting the model's parametric knowledge
  produces a larger drop than irrelevant context does
  ([2504.13079](https://arxiv.org/abs/2504.13079)). A dictionary entry disagreeing with a model about
  a word's senses is precisely this case.
- The spike doc's own prediction, written before any of this was read, and worth quoting because it
  anticipated the finding: *"Wiktextract entries are inconsistently formatted, Tatoeba sentences are
  uneven in quality and register, and both are structured for a machine that wants coverage rather
  than a learner who wants one good example."*

### One grounding defect already found and fixed

Worth keeping as an example of how a retrieval bug hides: **the reference lookup missed every gendered
noun.** It looked up `headword`, and Acervo stores `la azafata` because that is how a learner needs to
see the word — while a dictionary is keyed on `azafata`. The fix was to look up `lemma` as well. A
retrieval system that silently returns nothing looks identical to one whose source has no entry.

---

## §7 · Methodology already paid for

Each of these was learned by being wrong about it once.

- **Pairwise "which is better" is the wrong instrument for near-identical outputs.** Measured: a
  **50% false-positive rate on same-arm controls**, κ ≈ −0.10 against a Pro-model judge, and 15 of 18
  calls "slight". Prefer an instrument with right answers wherever one exists.
- **The option set is part of the instrument.** That 50% conflates *"I can see these are not the
  same"* with *"one is better"*, because the screen offered no way to say **both differ, neither is
  better** — the case the rater actually kept hitting. A flawed response set produces a clean-looking
  number.
- **Human raters have position bias too.** 14 right against 4 left, with side randomised against arm.
  Randomisation does not remove the bias; it only makes it measurable.
- **Measure the noise floor before the effect.** The within-arm variance across repeats is what made
  ten null results readable rather than arguable.
- **Pre-register thresholds and score them with a `missed` column** — including the ones drawn too
  tight to resolve. Note characters missed a 90% bar at 89.4% on a metric whose difference is a
  quarter of its own noise; the bar was wrong, not the prompt.
- **Ship conditions before code**, from
  [`translation-completeness-check.md`](translation-completeness-check.md): zero false rejections with
  N stated, no borrowed constants, and *a script class with no data ships no check for that class*.
- **A class of failure that no metric names is a class that cannot be reported** — from
  `clip-translation`'s postscript, where the shipped rewrite introduced a failure the experiment had
  no instrument for.
- **A check is the guarantee a prompt cannot give.** Also from `clip-translation`: *"a prompt is a
  request and this is a check."* The exact-copy refusal needs no threshold and no language table,
  which is why it works.
- **Controls make a subjective instrument self-validating.** Same-arm pairs, unlabelled, are the
  cheapest way to learn what a rater's zero looks like.

---

## §8 · The experiment backlog

Wide on purpose. Nothing here is scheduled.

| # | question | instrument | cost | what it teaches, including on a null result |
| --- | --- | --- | --- | --- |
| 1 | How often is each model wrong, per field? | §1 ground-truth harness, 30–50 words × 3–4 pairs | ~$2 | The prerequisite for every other row. A null result says quality is not the bottleneck. |
| 2 | Does a dictionary disagree with the model about `ipa`, and how often? | Compare generated `ipa` against `kaikki-*`, per language | free | Whether §3 closes issue 1, or whether the dictionary is the one that is wrong. |
| 3 | Does an in-chain check route to a better model, in practice? | Add the gloss-script check, measure how often a pair is demoted and whether the next answers correctly | free | Whether quality cascades work at all on real traffic. A null result (the next model is wrong too) is equally informative. |
| 4 | Can sampling detect a wrong field? | k samples from one model per field, agreement versus truth | ~$1 | Expected to **fail**, given 6-of-6 on `/ˈaska/`. A clean counterexample to SelfCheckGPT's assumption on structured fields. |
| 5 | Can cross-model voting detect it? | 3 pairs per field, majority versus truth | ~$3 | The counterpart to row 4, and the tension with Self-MoA. |
| 6 | Does check-triggered repair fix the field without damaging the rest? | CRITIC-shaped correction call, with a re-score of the whole article | ~$1 | Tests whether a narrow repair stays narrow. |
| 7 | Does ungrounded review help, against the literature? | Unconditional review step on §0's criteria | ~$2 | Reproduces or refutes [2310.01798](https://arxiv.org/abs/2310.01798) on real articles. |
| 8 | Does decontextualised verification beat in-context review? | CoVe-style independent questions versus "is this right?" | ~$2 | Tests the mechanism, not just the outcome. |
| 9 | What does the grounding we shipped do? | §6, three arms, sense-count negative check | ~$3 | Evaluates a shipped, disliked, unmeasured feature. |
| 10 | Is a judge measuring correctness or fluency? | Judge scores versus ground-truth field accuracy on the same articles | ~$2 | Tests [2410.21819](https://arxiv.org/abs/2410.21819)'s perplexity explanation where truth is known. |
| 12 | Does a per-field rubric agree with itself across raters? | The same articles scored twice, by a model and by hand | time | Establishes whether §0's rubric is usable before it is relied on. |

---

## §9 · The reading list

| paper | claim | what it implies here |
| --- | --- | --- |
| [2601.01842](https://arxiv.org/abs/2601.01842) · Towards Automated Lexicography | Definition generation for learner's dictionaries, judged on truthfulness, coverage, sense specificity, guideline compliance | §0's rubric, aimed at exactly this artifact |
| [2410.03182](https://arxiv.org/abs/2410.03182) · Bilingual example sentences | GDEX criteria; quality degrades for lower-resourced languages; **low inter-annotator agreement** | Explains κ ≈ 0, and predicts trouble for Russian and Chinese |
| [2404.06224](https://arxiv.org/abs/2404.06224) · Dictionary example sentences | LLM-generated examples often preferred to a published dictionary's | The examples may already be good; measure before improving |
| [2310.01798](https://arxiv.org/abs/2310.01798) · Cannot Self-Correct Yet | Intrinsic self-correction without external feedback can degrade output | Do not build "review your own article" |
| [2305.11738](https://arxiv.org/abs/2305.11738) · CRITIC | Tool-interactive critiquing does improve output | Build check-triggered repair instead |
| [2309.11495](https://arxiv.org/abs/2309.11495) · Chain-of-Verification | Verification questions answered **independently** of the draft reduce hallucination | The remedy for "conditioned on its input" |
| [2305.14251](https://arxiv.org/abs/2305.14251) · FActScore | Atomic-fact decomposition, scored against a reliable source | An article decomposes into per-claim verdicts |
| [2303.08896](https://arxiv.org/abs/2303.08896) · SelfCheckGPT | Black-box detection by sampling consistency — no logprobs needed | Assumes divergence; `/ˈaska/` is a counterexample |
| [2306.13063](https://arxiv.org/abs/2306.13063) · Confidence elicitation | Verbalised confidence is poorly calibrated | Why the logprob gap is not closed by asking |
| [2404.13076](https://arxiv.org/abs/2404.13076) · Favour their own generations | Judges recognise and prefer their own output | Never judge with a model that is also an arm |
| [2410.21819](https://arxiv.org/abs/2410.21819) · Self-preference bias | Judges prefer lower-perplexity, more familiar text | A judge may measure fluency, not correctness |
| [2305.05176](https://arxiv.org/abs/2305.05176) · FrugalGPT | Cascades cut cost at equal or better quality | Acervo's chain is a cascade already; make it quality-triggered |
| [2406.04692](https://arxiv.org/abs/2406.04692) · Mixture-of-Agents | Aggregating several models beats one | The case for cross-model consensus |
| [2502.00674](https://arxiv.org/abs/2502.00674) · Self-MoA | Repeated sampling from one strong model often beats mixing | The counter-case; verification and generation differ |
| [2408.02442](https://arxiv.org/abs/2408.02442) · Let Me Speak Freely? | Format restrictions degrade reasoning | Corroborates the constrained-decoding decision |
| [2504.13079](https://arxiv.org/abs/2504.13079) · Conflicting evidence in RAG | Knowledge conflict hurts more than noise | Why a dictionary can make an article worse |
| [2312.10997](https://arxiv.org/abs/2312.10997) · RAG survey | The landscape, including retrieval that harms | Background for §6 |
| [2606.11639](https://arxiv.org/abs/2606.11639) · IPA transcription bias | Soft PER, tolerating similar phoneme substitutions | How to compare `/ˈas.ko/` with `/ˈasko/` |
| [1708.01464](https://arxiv.org/abs/1708.01464) · Multilingual G2P | Neural grapheme-to-phoneme at scale | The alternative to a dictionary for `ipa` |

---

## The defect register

The original contents of this file. One section per defect, with evidence and what would settle it.

### 1 · A wrong IPA vowel, reproducibly, from the model that writes the articles

`el asco` → `/ˈaska/`. Spanish has **no vowel reduction**: an unstressed final `o` is `/o/` and never
`[a]`. The answer is `/ˈasko/`.

| pair | what it wrote for `el asco` |
| --- | --- |
| `gemini-free` / `gemini-3.5-flash-lite` | `/ˈaska/` — **6 of 6 calls**, both arms, all three repeats |
| `cloudflare` / `llama-3.3-70b` | `/ˈasko/` — correct, every call |
| `vertex` / `gemini-3.8-flash` | `/ˈasko/` and `/ˈas.ko/` — correct, every call |

**Deterministic** on that pair, so systematic rather than sampling noise — and that pair is first in
the text chain, so it is the model writing real articles. It was also the **only** wrong Spanish final
vowel in 315 calls, so this is not a general weakness in transcription; it is this word on this model,
which is the harder kind to find by sampling.

Fixes, in increasing order of cost: a prompt sentence about Spanish vowel reduction; **deriving or
omitting** `ipa` for languages whose orthography determines it; validating against the compiled
dictionary (§3); or the in-chain check that demotes the model (§2). The last two are the only ones
that close it.

### 2 · A pinyin tone error, not reproducibly

`麻烦` is `máfan` — second tone then neutral. `gemini-free` wrote `máfán` once in six calls, two second
tones. Cloudflare and Vertex were correct every time, and so was gemini in its other five.

Low frequency, but `reading` is **required** for Chinese and is the field a learner leans on hardest,
since the characters give them nothing. CC-CEDICT closes it mechanically (§3).

### What is already good, so it is not re-litigated

From the same 315 calls, the prompt's structural rules held on every pair:

- `dialect` — `che` → `es-AR` on all three pairs; nothing else marked regional.
- `register` — `currar` → colloquial or slang everywhere, never neutral.
- `pos` — `ничего` → expression on all three.
- `reading` present for every Chinese entry; its absence is a hard refusal and never fired.
- Gloss-language completeness **100% in both arms on every pair**.
- `shortGloss` never degenerated, and `primaryGloss` was a single term in all 158 usable replies.

The one structural rule that failed is the gloss **language**, and only on `llama-3.3-70b`, which
answered in English 28% of the time for vocabularies glossing into Russian first — a fact about one
model, and row 3 of the backlog.

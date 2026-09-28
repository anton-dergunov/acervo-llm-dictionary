# Clip selection · first readings

**Status:** first readings, not a measurement. Five runs of the real pipeline against the real corpus
and a real provider, read by eye. The method `docs/plans/quality/clip-selection.md` calls
for — 25–40 lexemes, a labelled rubric, precision and recall with stated denominators — has **not**
been carried out. What is here is the smaller thing worth doing before it: does v1 of the prompt
work at all, and is anything obviously broken.

| | |
| --- | --- |
| Prompt | `prompts/acervo_clip_select.md` — v1 (round 1), + a cut-quality section (rounds 2–3), + the rewrite below (round 4) |
| Model | `gemini/gemini-3.1-flash-lite`, through `acervo.models` on the chain `gemini-free` |
| Corpus | spoken-usage-retrieval 0.2.0, Spanish, 251 videos / 60,704 segments, index built 11 Sep 2026 |
| Candidates | 20, `match_mode=auto`, `order=ranked` — the shipped configuration, unvaried |
| Words | 8 Spanish lexemes, 14 senses, chosen for polysemy and for colloquial register |
| Run directory | scratch only; the runner and its JSON are not tracked |

## What the numbers were

| Run | Prompt | Senses filled | Hallucinated ids | Median |
| --- | --- | --- | --- | --- |
| 1 | v1 | 11 / 14 | 0 | 2.6 s |
| 2 | v1 + cut-quality | 10 / 14 | 0 | 1.5 s |
| 3 | v1 + cut-quality | 9 / 14 | 0 | 5.2 s |
| 4a | `selfContainedOnly` **off** — the shipped default | 12 / 14 | 0 | — |
| 4b | `selfContainedOnly` **on** | 12 / 14 | 0 | — |

**Nothing hallucinated a segment id in any run.** That is the one number the drop-and-count path
exists to surface, and at this scale it is zero — which is worth knowing before deciding whether the
counter is load-bearing or merely cheap insurance.

## The one failure worth changing the prompt for

Round 1 selected two passages that were **cut badly** rather than wrongly chosen. The sense was
right and the word was used properly; the passage simply did not begin or end at a sentence
boundary:

> *"era un castillo un poco pijo, pero sí, trabajaba de camarera en un castillo que celebraba bodas.
> Y en el castillo nos daban un traje que picaba mucho, picaba mucho y era de color gris con"*

Chosen for *picar* = "to itch", and the clause in the middle is a perfect example of it. But the
passage starts mid-thought and trails off mid-phrase, and the learner is shown the whole of it.

The same shape appeared for *quedar* = "to remain":

> *"enfermedades posibles, literal, la puertita, estaba así el flaco y me dice, «Usted, este tipo se
> tiene que quedar acá 48 horas mínimo en reposo.»"*

v1 did tell the model to reject these — but in one bullet, fourth in a list, competing with
"the word is doing real work in it". The diagnosis is that **the model was judging the best clause
inside the passage rather than the passage it was choosing.**

The change was to make that check first, name it as the most common failure, give it a concrete
three-part test (does it begin where a sentence begins, does it end where one ends, is it one
thing), quote both real failures back, and say plainly: *you are choosing the passage, not editing
it.* Rounds 2 and 3 produced **no ragged passages at all**, and *picar* = "to itch" — whose only
good use in this corpus is inside that ragged castle passage — is now correctly refused.

## What did not need changing

- **Sense discrimination is good.** *pillar* was told apart as "to catch" and "to grasp" in every
  run; *quedar* as "to remain" and "to arrange to meet"; *bronca* as "anger" and "a row". This is
  the judgement the whole design spends a frontier call on, and it is the part that works.
- **The translations are usable as they stand**, and `matchedTranslationForm` held verbatim in
  every case — *itchy*, *bit*, *arrange to meet*, *worked hard*, *grasping*.
- **Refusing is being used.** Three to five senses per run got nothing, without prompting.

## Variance, and why it is the right kind

Rounds 2 and 3 share a prompt and disagree on three of eight words. Every disagreement is at the
borderline — *currar*'s single candidate taken in one run and refused in the other, *bronca*'s
second sense filled in one and not the other — and no run produced something plainly bad. Variance
concentrated at the margin is what a well-calibrated threshold looks like; variance in the middle
would not be.

The fill rate drifting 11 → 10 → 9 is therefore **not** evidence that the prompt got stricter twice.
Round 3 is the same prompt as round 2.

## What this does not tell you

- Whether precision is *high enough*. Eight words read by one person is an impression.
- Anything about recall. Nobody read the declined candidates to ask whether a good one was passed
  over, which is half of what the experiment document asks for.
- Anything about the knobs. Candidate count, what a candidate carries, what a sense carries and how
  refusal is framed were all held at their shipped values; the experiment document names them in
  the order to vary them.
- Anything about a second language. The corpus indexes only Spanish.

## What to do next

Carry out the real loop in `docs/plans/quality/clip-selection.md` — 25–40 saved lexemes, labels
on both selections *and* refusals, and one knob at a time starting with candidate count. This round
supplies the starting point and one fix, not a baseline to stop at.

---

# Round 4 · the rule was testing the wrong thing

Rounds 2 and 3 rejected two passages. Reading them side by side with the owner showed that **only
one of them is bad**, and that the rule was catching them for the wrong reason.

> *"era un castillo un poco pijo, pero sí, trabajaba de camarera en un castillo que celebraba bodas.
> Y en el castillo nos daban un traje que picaba mucho, picaba mucho y era de color gris con"*

Begins mid-sentence, trails off — and is **fine**. Someone worked as a waitress at a castle; the
uniform itched. It is longer than it needs to be and you have to hunt for the word, but nothing is
missing and you can follow all of it.

> *"enfermedades posibles, literal, la puertita, estaba así el flaco y me dice, «Usted, este tipo se
> tiene que quedar acá 48 horas mínimo en reposo.»"*

Also begins mid-sentence — and is **not** fine. It opens on possible illnesses and a little door.
Who is ill, whose door, where this is happening: you can invent a hospital and a doorway, and having
to invent them is the problem.

The two are indistinguishable by punctuation and obvious by comprehension. So the rule was rewritten
to ask **can a person follow this without guessing what came before**, quoting both passages — the
*quedar* one as the failure and the castle one as an acceptable case that is merely long.

## It works, and the distinction is the evidence

| | round 4a (off) | round 4b (on) |
| --- | --- | --- |
| *picar* — castle passage | kept | **kept** |
| *quedar* — ragged opening | kept | **replaced** with *"Eso quiere decir que me puedo quedar en Europa el tiempo que yo quiera."* |
| Senses filled | 12 / 14 | 12 / 14 |

The old punctuation rule rejected both passages. The new one keeps the readable one and drops the
unrecoverable one — which is the whole distinction, made by the model, from the rewritten text.

It also costs **no recall**: 12 of 14 either way, against 9–11 under the old rule. That is what a
rule aimed at a narrow real failure looks like, next to one aimed at a proxy for it.

## And it ships **off**

Not because it does not work, but because a clip exists to show the language as it is actually
spoken. In real life you walk into a room where somebody is already talking and you do not ask them
to start again; the corpus is curated toward exactly that kind of conversation, where people talk
over each other and start mid-thought. Discarding those by default would quietly bias the whole
feature toward scripted teaching content — which is what the channel figures below were already
hinting at.

`clip_settings.self_contained_only` turns it on for a learner who wants the steadier version. The
section lives behind `<!-- if: selfContainedOnly -->` in the prompt file, so it is readable in place
rather than assembled in code.

## The channel bias, which is real and is not this rule's doing

Across all five runs the candidate pool was **84% automatic captions** (76 of 91), but manual-caption
channels took **30–45%** of the selections — including round 1, before any cut rule existed, and
round 4a with the rule off.

So the model prefers cleanly captioned, more scripted sources on its own. That is a finding for
`docs/plans/quality/clip-selection.md` to measure properly, not something to correct by prompt here. It is
also the strongest argument for shipping the passage rule off: it would have pushed the same
direction the model already leans.

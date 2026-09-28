# Grounding spike — does conditioning on external sources make a better entry?

**Status:** the spike is unrun, but **grounding shipped without it** — so the question this document
asks has moved from *should we?* to *what does the one we built actually do?*

**When, and how big.** After the dictionary survey ([`../dictionaries.md`](../dictionaries.md) §1),
since the sources it would ground on are the ones that survey is replacing — and small: twenty words
at most. The likeliest outcome is that grounding is switched off, and a quick spike is the honest way
to reach that rather than a slow one.

`services/capture/coerce.py:reference_of` carries an external dictionary's entry into the compose
request, and `prompts/acervo_compose.md` governs it under two treatments, **STAY CLOSE TO THE
REFERENCE** and **FILL IN THE GAPS**. It is reached from "Add to my words" on an external article.
What was never built is the comparison: no arm, no review, no measurement. The owner has used it and
dislikes the articles it produces, which is an impression rather than a finding, and the reason to
evaluate it rather than to close this.

The re-scoped experiment — three arms, and *sense inflation* as the failure mode rather than recall —
is [`article-quality.md`](article-quality.md) §6. The design below still applies; only
its premise that nothing consults an external source is out of date.

## The question

A confident claim, and the reason grounding was built:

> **Pass the Wiktextract sense inventory and 2–3 real attestations into the generation prompt as
> grounding.** That demotes the model from *knowledge source* to *selector and formatter*, where
> hallucination risk on this kind of task is close to zero.

The reasoning behind it is sound — LLM prose uses a measurably narrower vocabulary than human
writing, and a model handed `picar` will give you the two obvious meanings and silently drop five
others that Wiktionary has.

But the claim was made before anyone looked at what those sources actually contain. Reading them,
the counter-argument is not weak: Wiktextract entries are inconsistently formatted, Tatoeba
sentences are uneven in quality and register, and both are structured for a machine that wants
coverage rather than a learner who wants one good example. A large model may simply write a better
article than either, and stuffing a badly-formatted sense inventory into the prompt may cost quality
rather than buy it.

**So this is a spike, not a feature.** Build the comparison, look at real output over real
vocabulary, and let the answer decide whether §09's grounding paragraph survives.

> **It is probably worth running this after external dictionaries (§08) land, not before.**
> §08 puts local dictionary files on the server for reading. Once those exist they are a third
> grounding candidate, and a better one than Wiktextract — curated, consistently formatted, and
> already chosen. Running the spike now answers a smaller question than running it later.

## What gets compared

Two variants of the same entry, for the same word, from the same input text:

| Variant | Prompt |
|---|---|
| **A — ungrounded** | Exactly what `prompts/acervo_compose.md` sends today. |
| **B — grounded** | The same prompt plus a grounding block: the source's sense inventory, and 2–3 attested sentences. |

Everything else is held constant: same model, same temperature, same word, same learner sentences,
same topic list. The only variable is the grounding block.

## Sources to try

- **Wiktextract** — machine-readable Wiktionary. The sense inventory is the thing §09 wants; the
  formatting is the thing to be suspicious of.
- **Tatoeba** — human-contributed sentence pairs. Directly targets the weakness §09 names (bland
  model examples), and directly risks the failure it does not (uneven register, odd topics).
- **Local dictionaries (§08)**, once they exist. Likely the strongest candidate and the reason to
  delay.

Each is worth measuring **separately** as well as together — "grounding helps" and "Wiktextract
helps" are different findings, and only the second tells you what to build.

## Input

Real vocabulary, not invented examples: a sample drawn from the notes the ingest script already
walks (`~/obsidian/Languages/…`), deliberately skewed towards the words where the two variants
should diverge —

- heavily overloaded words (`picar`, `dar`), where a dropped sense is the failure grounding claims to fix;
- idioms and slang (`ni en pedo`), where Wiktionary coverage is thin and register matters;
- ordinary concrete nouns (`el cuchillo`), where grounding should make **no** difference — and if it
  does, it is adding noise;
- a handful in each vocabulary language, since coverage differs sharply between them.

Fifty pairs is enough to see a pattern and few enough to actually review.

## The review page

The evaluation happens on the tablet, so the page is built for it:

- served over the local network — `python -m http.server --bind 0.0.0.0` from the output directory;
- one word per screen, **two cards side by side**, A and B;
- **blind**: which side is grounded is randomised per word and recorded only in the answer file, so
  the reviewer cannot drift towards a preferred variant;
- three buttons — *left better*, *right better*, *no real difference* — plus an optional note;
- choices written to a ratings JSON as they are made, so an interrupted session resumes.

"No real difference" is a first-class answer, not a cop-out. If it wins on most words, grounding is
not worth its cost regardless of how it does on the rest.

## What would settle it

Grounding earns its place only if it does something the ungrounded variant cannot:

- **Coverage** — grounded entries carry senses the ungrounded one omitted, and those senses are ones
  worth having. Count them; this is the strongest form of the §09 claim and the easiest to check.
- **Examples** — grounded examples read as language someone would actually use, rather than textbook
  sentences. This is the claim §09 rests on and the hardest to measure, which is why it is judged by
  eye rather than scored.
- **No regression** — grounded entries are not *worse* on the simple words. A source that adds
  senses to `picar` and clutter to `el cuchillo` is a source to apply selectively, not globally.

If grounding wins clearly, wire it as a per-source server setting and record the decision in §09. If
it wins only on overloaded words, wire it conditionally. If it does not win, delete the grounding
paragraph from §09 and say why — a documented negative result is worth more than an unexamined
recommendation.

## Not part of the spike

Storage, sync and the capture endpoint are untouched: the spike is a script that writes files and a
page that reads them. It does not write to the vocabulary graph, and nothing it produces is kept.

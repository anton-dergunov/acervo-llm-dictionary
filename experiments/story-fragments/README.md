# Story fragments: why a voice said more than its passage, and how to catch it

Serves story narration (`src/acervo/services/story_audio.py`, `docs/features/stories.md`, "Read aloud
in one voice"). Follows up the one fault [`take-verification/`](../take-verification/README.md) found
outside loops.

## The question

On 24 Sep 2026 the narration step cut «Sin mostrar ningún temor,» as a passage of its own, and the
voice read it as 10.96 s of speech, finishing the sentence with words that are in no story («…el joven
luchó contra aquellos seres con una gran ferocidad. Se sabía defender con arte.»). The obvious fixes
were to stop the segmenter ending a passage on a comma, or to refuse a recording far longer than its
text. Two questions before choosing: **is it the cut, or the voice?** And **which check catches it
without building in a choice that holds for one language?**

## Is it isolated? (the stored passages)

All 388 story passages then stored, from `take-verification`'s manifest — Spanish, every one by
`gemini-3.1-flash-tts-preview`, voice Fenrir:

- 8 end mid-sentence, as the segmenting prompt allows ("split a long sentence only where the feeling
  changes"). **7 of the 8 were read correctly**: 0.9–1.7× the median seconds per character.
- The one failure is the shortest fragment, four words, at **5.2×**. The highest of the other 387 is 1.7×.

So it was not the comma. A rule about punctuation would also be a list of marks — «，», «、», «،», and
nothing at all for Thai — guarding against a voice's habit in a step that knows nothing of voices.

## 1 · The same request again (`record.py`, `hear.py`)

The request was rebuilt from git at the commit then live (a3aec2f): the story template with no accent
(accents arrived 4 Nov), LINEAR16, voice Fenrir, the same direction. **The take key computed from those
parameters is the name of a file in the server's take store, written at 18:17:02 that day**, so they
are the parameters, not a guess at them. One thing could not be kept: the bare `es` language code is
now refused for Gemini voices, so `es-ES` was sent, which is what today's code sends for Spanish with no
accent. Ten takes of the fragment and ten of it joined to its next passage, on the model that recorded
the story and on the one behind it in the chain; each heard by Whisper base and small (`hear.py`).

| Model | Fragment wrong | Joined wrong |
| --- | --- | --- |
| gemini-3.1-flash-tts-preview | **0 / 10** (the original is the 1 wrong of 11) | 0 / 10 |
| gemini-2.5-flash-tts | **8 / 10** | 3 / 10 |

The invention did not come back on 3.1. The fallback did something else: it **read its direction
aloud, in Spanish**, and often the template's last sentence after it — «sin mostrar ningún temor con un
hinto de defiancia», «… No deas, drop, translate o explain any words.» (5.1–14.3 s for four words). On a
whole sentence it did so less, but it did.

## 2 · Which check (`variants.py report`, and the stored passages)

| Check | Wrong takes caught | False alarms |
| --- | --- | --- |
| Length, 3× the clean takes' median for the same text | 6 of the 12 wrong in step 1 | 0 |
| The loop rule (`hearing.rule.leaked`: words of the English direction around the text) | 3 of 12 | 0 |
| **Words heard outside the text's own stretch** (`hearing.rule.around`), ≥ 3 | **12 of 12** in step 1; all but the case below in step 3 | **1 of 948** |

The loop rule misses because Whisper writes the leak in the story's language: «hint of defiance» comes
back «hinto de defiancia», which is not a word of the direction. Length misses because a five-word leak
only doubles a short passage — even at 2× it catches 10 of 12, against a median of clean takes of the
very same text that a story being recorded does not have. Words outside the text need no list in any language. Over the 388 stored
passages, Whisper base hears one word outside one of them and none outside the rest; the bad passage is
heard with 15. The threshold was first 4; three wrong takes at exactly 3 («sin mostrar ningún temor,
seguirán con todo.») moved it to 3, where the only right take that reaches it is a shouted line in an
Argentine accent that Whisper could not follow («¡Y tu eres un edad fah!» for «¡Esto es una estafa!»):
one extra take. Text written without spaces is compared by character, decided by its Unicode script
(`hearing.rule.by_character`) — six characters, a threshold no recording has measured yet.

**Not caught**: a direction said *instead of* the text's first words. On 2.5, «El viajero alzó la vista y
vio…» came back «Tenso y dramático, y vio…» (direction "Tense and dramatic") in 7 of its 80 takes of
that sentence, at the normal length, so it replaced the words rather than adding to them. The alignment reads
«Tenso y dramático» as a mishearing of the words it replaced. A rule for missing words — the longest run
of the text's words not heard — reaches 4 on all seven, but also on 10 of the 50 shouted 3.1 lines and on
a stored passage where Whisper wrote «mil ochocientos noventa» as «1890». Left as a known gap.

## 3 · Does the prompt fix it? (`variants.py`)

Five story templates, both voices, four passages (the fragment, a dialogue fragment «"¡Esto es una
estafa!",» and two whole sentences), ten takes each, through today's request path (`speak.direction`,
`speak.speak`) for `es-AR`, the accent the vocabulary has now; then the three closest on 2.5 with no
accent (`es`). Heard by the server's own ear (`acervo.hearing`, Whisper base on CTranslate2). Wrong is
three or more words outside the text. 7 refusals as against Vertex's usage guidelines passed on a retry.

| Language | Model | Template | Wrong | Fragment | Quote | Sentence 1 | Sentence 2 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| es-AR | 3.1 | **current** | 0/40 | 0/10 | 0/10 | 0/10 | 0/10 |
| es-AR | 3.1 | no-guard | 0/40 | 0/10 | 0/10 | 0/10 | 0/10 |
| es-AR | 3.1 | bare | 0/40 | 0/10 | 0/10 | 0/10 | 0/10 |
| es-AR | 3.1 | say-following | 0/40 | 0/10 | 0/10 | 0/10 | 0/10 |
| es-AR | 3.1 | say-only | 1/40 | 0/10 | 1/10 | 0/10 | 0/10 |
| es-AR | 2.5 | **current** | 1/40 | 1/10 | 0/10 | 0/10 | 0/10 |
| es-AR | 2.5 | no-guard | 2/39 | 2/9 | 0/10 | 0/10 | 0/10 |
| es-AR | 2.5 | bare | 7/40 | 7/10 | 0/10 | 0/10 | 0/10 |
| es-AR | 2.5 | say-following | 11/40 | 4/10 | 1/10 | 6/10 | 0/10 |
| es-AR | 2.5 | say-only | 1/40 | 1/10 | 0/10 | 0/10 | 0/10 |
| es | 2.5 | **current** | 9/40 | 9/10 | 0/10 | 0/10 | 0/10 |
| es | 2.5 | no-guard | 13/40 | 10/10 | 2/10 | 0/10 | 1/10 |
| es | 2.5 | say-only | 9/40 | 9/10 | 0/10 | 0/10 | 0/10 |

(The 3.1 say-only quote is the shout Whisper could not follow, not a wrong take.)

- **The shipped template stays.** No variant beats it; dropping its closing sentence ("Do not add, drop,
  translate or explain any words.") does worse even though that is the sentence the voice reads out, and
  a template with nothing but the direction does worse again.
- **The accent sentence protects the fallback**: with it, 1 fragment in 10 goes wrong; with no accent
  chosen, 9 in 10, under every template tried. Whole sentences mostly come through either way. So **the
  fragment is the trigger**, a prompt cannot remove it, and joining a fragment to its neighbour is the
  remedy that fits: in step 1, the joined passage went wrong in 3 of 10 where the fragment alone did in 8.
- 3.1 got 200 takes right whatever it was sent.

## What shipped

A passage sent a direction is heard by the server's Whisper; three words outside its own stretch (six
characters, by character) and it is recorded once more by the same voice, then joined to its neighbour,
then kept; each step is a line in `admin log --failed`. The segmenting prompt and the voice template are
unchanged. The design is in `docs/features/stories.md`.

## Running it

```bash
.venv/bin/python experiments/story-fragments/record.py --takes 10           # step 1, the old request
experiments/take-verification/.venv/bin/python experiments/story-fragments/hear.py --model base
.venv/bin/python experiments/story-fragments/variants.py record --takes 10  # step 3, es-AR
.venv/bin/python experiments/story-fragments/variants.py record --takes 10 --language es \
    --model gemini-2.5-flash-tts --variant current --variant no-guard --variant say-only
.venv/bin/python experiments/story-fragments/variants.py report
```

Vertex through the laptop's `providers.local.json` (`vertex`). Takes go to `out/` (ignored); the
transcripts, lengths and scores are in `results/`: `takes.jsonl` and `heard-{base,small}.jsonl` for step
1, `variants.jsonl` for step 3.

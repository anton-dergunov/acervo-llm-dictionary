# Take verification: results

82 of 82 clips judged: 6 wrong, 75 right, 1 unsure.

Controls (random clips the loosest rule passed): 12, of which wrong: 0.

## The rule: words of the direction heard around the text

Fires when Whisper hears, outside the text's own stretch, a word of the direction that was sent (`sweep.leak`). One row per model; precision from the labels.

| model | clips | fired | wrong | right | unsure | unjudged |
| --- | --- | --- | --- | --- | --- | --- |
| base | 2445 | 3 | 3 | 0 | 0 | 0 |
| small | 2445 | 3 | 3 | 0 | 0 | 0 |
| turbo | 382 | 3 | 3 | 0 | 0 | 0 |

## The first rule, rejected: distance and likelihood

`twice OR instruction OR (cer_inner > τc AND gap > τg)`. It raises what an emotional delivery does to a transcript, which the owner judged right in every case.

## base

Each cell: flagged loop lines · wrong / right / unsure among them · precision.

| τc \ τg | 0.25 | 0.5 | 0.75 | 1.0 | 1.5 |
| --- | --- | --- | --- | --- | --- |
| 0.2 | 180 · 5/42/1 · 0.11 | 128 · 5/38/1 · 0.12 | 97 · 5/34/1 · 0.13 | 74 · 5/30/1 · 0.14 | 47 · 5/20/0 · 0.20 |
| 0.3 | 130 · 5/40/1 · 0.11 | 94 · 5/36/1 · 0.12 | 76 · 5/33/1 · 0.13 | 63 · 5/29/1 · 0.15 | 41 · 5/20/0 · 0.20 |
| 0.4 | 87 · 5/34/1 · 0.13 | 63 · 5/32/1 · 0.14 | 53 · 5/31/1 · 0.14 | 43 · 5/27/1 · 0.16 | 30 · 5/19/0 · 0.21 |
| 0.5 | 52 · 5/28/1 · 0.15 | 40 · 5/27/1 · 0.16 | 36 · 5/26/1 · 0.16 | 29 · 5/23/1 · 0.18 | 21 · 5/16/0 · 0.24 |
| 0.6 | 38 · 5/17/0 · 0.23 | 28 · 5/17/0 · 0.23 | 24 · 5/16/0 · 0.24 | 19 · 5/14/0 · 0.26 | 16 · 5/11/0 · 0.31 |
| 0.8 | 19 · 5/8/0 · 0.38 | 15 · 5/8/0 · 0.38 | 14 · 5/8/0 · 0.38 | 12 · 5/7/0 · 0.42 | 11 · 5/6/0 · 0.45 |

Where each clip judged wrong ranks (structural flags first, then cer × gap): `story/i2zsofjyz15psgk-02` –, `take/7c79e8cb2ff04516` 1, `take/d13875be2093a251` 7, `take/d1f1295ec2370ae9` 2, `take/e7ebf430489737a3` 5, `take/f712795794164308` 4

Laptop (M1, MPS): median 0.17 s to transcribe, 0.08 s to score the text.

## small

Each cell: flagged loop lines · wrong / right / unsure among them · precision.

| τc \ τg | 0.25 | 0.5 | 0.75 | 1.0 | 1.5 |
| --- | --- | --- | --- | --- | --- |
| 0.2 | 103 · 4/39/1 · 0.09 | 80 · 4/38/1 · 0.10 | 59 · 4/35/1 · 0.10 | 42 · 4/26/1 · 0.13 | 22 · 4/14/0 · 0.22 |
| 0.3 | 79 · 4/39/1 · 0.09 | 61 · 4/38/1 · 0.10 | 47 · 4/35/1 · 0.10 | 34 · 4/26/1 · 0.13 | 18 · 4/14/0 · 0.22 |
| 0.4 | 55 · 4/37/1 · 0.10 | 46 · 4/36/1 · 0.10 | 38 · 4/33/1 · 0.11 | 30 · 4/25/1 · 0.14 | 18 · 4/14/0 · 0.22 |
| 0.5 | 38 · 4/28/1 · 0.12 | 33 · 4/28/1 · 0.12 | 31 · 4/26/1 · 0.13 | 25 · 4/20/1 · 0.17 | 14 · 4/10/0 · 0.29 |
| 0.6 | 23 · 4/15/0 · 0.21 | 19 · 4/15/0 · 0.21 | 18 · 4/14/0 · 0.22 | 14 · 4/10/0 · 0.29 | 10 · 4/6/0 · 0.40 |
| 0.8 | 10 · 4/3/0 · 0.57 | 7 · 4/3/0 · 0.57 | 6 · 4/2/0 · 0.67 | 6 · 4/2/0 · 0.67 | 5 · 4/1/0 · 0.80 |

Where each clip judged wrong ranks (structural flags first, then cer × gap): `story/i2zsofjyz15psgk-02` –, `take/7c79e8cb2ff04516` 1, `take/d13875be2093a251` 164, `take/d1f1295ec2370ae9` 2, `take/e7ebf430489737a3` 4, `take/f712795794164308` 3

Laptop (M1, MPS): median 0.58 s to transcribe, 0.27 s to score the text.

## turbo (reference: the page's clips and a random sample)

Each cell: flagged loop lines · wrong / right / unsure among them · precision.

| τc \ τg | 0.25 | 0.5 | 0.75 | 1.0 | 1.5 |
| --- | --- | --- | --- | --- | --- |
| 0.2 | 35 · 5/27/0 · 0.16 | 33 · 5/25/0 · 0.17 | 31 · 5/23/0 · 0.18 | 25 · 5/17/0 · 0.23 | 17 · 5/12/0 · 0.29 |
| 0.3 | 32 · 5/24/0 · 0.17 | 31 · 5/23/0 · 0.18 | 29 · 5/21/0 · 0.19 | 24 · 5/16/0 · 0.24 | 17 · 5/12/0 · 0.29 |
| 0.4 | 29 · 5/22/0 · 0.19 | 29 · 5/22/0 · 0.19 | 27 · 5/20/0 · 0.20 | 22 · 5/15/0 · 0.25 | 16 · 5/11/0 · 0.31 |
| 0.5 | 25 · 5/19/0 · 0.21 | 25 · 5/19/0 · 0.21 | 23 · 5/17/0 · 0.23 | 19 · 5/13/0 · 0.28 | 14 · 5/9/0 · 0.36 |
| 0.6 | 17 · 5/11/0 · 0.31 | 17 · 5/11/0 · 0.31 | 16 · 5/10/0 · 0.33 | 15 · 5/9/0 · 0.36 | 12 · 5/7/0 · 0.42 |
| 0.8 | 7 · 5/2/0 · 0.71 | 7 · 5/2/0 · 0.71 | 7 · 5/2/0 · 0.71 | 7 · 5/2/0 · 0.71 | 6 · 5/1/0 · 0.83 |

Where each clip judged wrong ranks (structural flags first, then cer × gap): `story/i2zsofjyz15psgk-02` –, `take/7c79e8cb2ff04516` 1, `take/d13875be2093a251` 4, `take/d1f1295ec2370ae9` 2, `take/e7ebf430489737a3` 5, `take/f712795794164308` 3

Laptop (M1, MPS): median 2.00 s to transcribe, 0.22 s to score the text.

## On the NAS (AMD Ryzen R1600, inside the acervo-server image)

| engine | model | threads | loop line | word | story passage | load |
| --- | --- | --- | --- | --- | --- | --- |
| ctranslate2 | base | 4 | 1.99 s (p90 2.56; audio 1.96 s) | 2.08 s (p90 2.17; audio 4.85 s) | 2.21 s (p90 2.30; audio 7.56 s) | 1.91 s |
| transformers | base | 4 | 4.08 s (p90 4.28; audio 1.96 s) | 3.68 s (p90 4.48; audio 4.85 s) | 4.23 s (p90 4.50; audio 7.56 s) | 12.72 s |
| ctranslate2 | small | 4 | 7.02 s (p90 7.20; audio 1.96 s) | 7.23 s (p90 7.51; audio 4.85 s) | 7.56 s (p90 7.83; audio 7.56 s) | 1.26 s |
| transformers | small | 4 | 15.47 s (p90 15.78; audio 1.96 s) | 13.33 s (p90 14.57; audio 4.85 s) | 14.37 s (p90 14.93; audio 7.56 s) | 14.98 s |

## Judged wrong

- `story/i2zsofjyz15psgk-02` «Sin mostrar ningún temor,» (es; asked: Calm and resolute, with a hint of defiance.) — words added; “Said “ Sin mostrar ningún temor, el joven luchó contra aquellos seres con una gran ferocidad. Se sabía defender con arte.” but you probably didn’t cut it right.”; raised by base:0.5/1.0, base:duration, small:0.4/0.75, small:duration
- `take/7c79e8cb2ff04516` «cough» (en; asked: Speak annoyed and raspy, seeking relief from irritation in the throat, but clearly, at a natural pace, with a natural pitch range.) — no fault named; “It said “I need a congestion relief “ obviously wrong, but we could keep this one potentially, it is funny a bit. But not what we want of course.”; raised by base:0.5/1.0, small:0.4/0.75
- `take/d13875be2093a251` «clumsy» (en; asked: Speak laughing affectionately at someone dropping their keys, gentle and amused, but clearly, slightly briskly, with a slightly brighter pitch.) — no fault named; “She didn’t say a word, just haha. That’s not too bad, because at least we repeat that multiple times, so just laughing is okay.”; raised by base:0.5/1.0, small:0.4/0.75
- `take/d1f1295ec2370ae9` «cough» (en; asked: Speak annoyed and raspy, seeking relief from irritation in the throat, but clearly, at a natural pace, with a natural pitch range.) — instruction read out; “Said “ Seek relief from irritation in the throat.” that one is bad and wrong”; raised by base:0.5/1.0, small:0.4/0.75
- `take/e7ebf430489737a3` «hit» (en; asked: Speak someone wincing at a sharp sudden impact, startled and pained, but clearly, at a natural pace, with a natural pitch range.) — a word changed, garbled; “I heard just uhh… The word was not said. But that is also more or less okay.”; raised by base:0.5/1.0, small:0.4/0.75
- `take/f712795794164308` «to provide» (en; asked: Speak a helpful host offering more food, warm and generous, but clearly, slightly slowly, with a natural pitch range.) — words added; “Said “to provide more””; raised by base:0.5/1.0, small:0.4/0.75

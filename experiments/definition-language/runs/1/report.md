# Definition language: runs/1

| Set | Model | Arm | Words | Senses | Wrong senses (certain) | Words with one wrong | Cost |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| control | gemini-3.5-flash-lite | after | 30 | 53 | 0 (0) | 0 (0%) | $0.070 |
| control | gemini-3.5-flash-lite | named | 30 | 49 | 0 (0) | 0 (0%) | $0.069 |
| sample | gemini-3.1-flash-lite | after | 105 | 172 | 0 (0) | 0 (0%) | $0.174 |
| sample | gemini-3.1-flash-lite | named | 105 | 170 | 0 (0) | 0 (0%) | $0.173 |
| sample | gemini-3.5-flash-lite | after | 105 | 183 | 5 (0) | 2 (2%) | $0.244 |
| sample | gemini-3.5-flash-lite | before | 105 | 176 | 109 (27) | 63 (60%) | $0.243 |
| sample | gemini-3.5-flash-lite | named | 105 | 177 | 4 (0) | 2 (2%) | $0.243 |

## Per vocabulary (sample, words with one wrong)

| Model | Arm | de-DE | es-ES | fr-FR | it-IT | ko-KR | pt-BR | ru |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| gemini-3.1-flash-lite | after | 0/15 | 0/15 | 0/15 | 0/15 | 0/15 | 0/15 | 0/15 |
| gemini-3.1-flash-lite | named | 0/15 | 0/15 | 0/15 | 0/15 | 0/15 | 0/15 | 0/15 |
| gemini-3.5-flash-lite | after | 0/15 | 2/15 | 0/15 | 0/15 | 0/15 | 0/15 | 0/15 |
| gemini-3.5-flash-lite | before | 8/15 | 12/15 | 7/15 | 10/15 | 10/15 | 12/15 | 4/15 |
| gemini-3.5-flash-lite | named | 0/15 | 2/15 | 0/15 | 0/15 | 0/15 | 0/15 | 0/15 |

## Paired comparisons (same words, per-word outcome)

- sample, gemini-3.5-flash-lite, before → after: 62 fixed, 1 broken over 105 words; McNemar p = 1.4e-17
- sample, gemini-3.5-flash-lite, before → named: 61 fixed, 0 broken over 105 words; McNemar p = 8.7e-19

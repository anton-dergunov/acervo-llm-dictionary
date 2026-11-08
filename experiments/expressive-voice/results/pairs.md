# Expressive voice, round 2: does a tag move ElevenLabs' accent?

Unblinded by `pairs.py report`: 32 of 32 pairs answered. Each pair is one text read under two accents; the owner said which sounds Argentine (Spanish) or British (English), or that they sound the same, or could not tell. Gemini's pairs are the calibration: they show whether the contrast can be heard in these texts at all.

## Spanish: Argentina against Spain

| Take | Pairs | Picked the Argentine one | Picked the other | The same | Can't tell | Verdict |
|---|---|---|---|---|---|---|
| v4-calm | 7 | 7 | 0 | 0 | 0 | **moves the accent** |
| v4-current | 7 | 6 | 0 | 1 | 0 | **moves the accent** |
| v4-named | 7 | 4 | 0 | 3 | 0 | does not move it |
| gemini | 7 | 7 | 0 | 0 | 0 | audible |

A tag moves the accent when the Argentine take is picked in at least 6 of its pairs and Gemini's pairs reach the same.

By whether the text holds «ll» or «y» before a vowel:

| Take | With ll/y: picked Argentine | Without: picked Argentine |
|---|---|---|
| v4-calm | 2/2 | 5/5 |
| v4-current | 1/2 | 5/5 |
| v4-named | 0/2 | 4/5 |
| gemini | 2/2 | 5/5 |

## English: British against American

| Take | Pairs | Picked the British one | Picked the other | The same | Can't tell | Verdict |
|---|---|---|---|---|---|---|
| v4-named | 2 | 0 | 0 | 2 | 0 | does not move it |
| gemini | 2 | 2 | 0 | 0 | 0 | audible |

A tag moves the accent when the British take is picked in at least 2 of its pairs and Gemini's pairs reach the same.

## Every pair

| Pair | Take | Text | Answer | Flags and note |
|---|---|---|---|---|
| p19 | gemini | The child clung to her father's hand in the crowde | target |  |
| p18 | v4-named | The child clung to her father's hand in the crowde | same |  |
| p28 | gemini | His polite manner was only a disguise for his ange | target |  |
| p11 | v4-named | His polite manner was only a disguise for his ange | same |  |
| p06 | gemini | decepcionar | target |  |
| p30 | v4-calm | decepcionar | target |  |
| p14 | v4-current | decepcionar | target | a01/v4-current/1: said twice |
| p05 | v4-named | decepcionar | target |  |
| p12 | gemini | hacer gracia | target |  |
| p01 | v4-calm | hacer gracia | target |  |
| p17 | v4-current | hacer gracia | target | a02/v4-current/1: said twice |
| p09 | v4-named | hacer gracia | target |  |
| p03 | gemini | la concienciación ecológica | target |  |
| p21 | v4-calm | la concienciación ecológica | target |  |
| p15 | v4-current | la concienciación ecológica | target |  |
| p07 | v4-named | la concienciación ecológica | target |  |
| p13 | gemini | Necesito sanar mis cargas emocionales. | target |  |
| p08 | v4-calm | Necesito sanar mis cargas emocionales. | target |  |
| p16 | v4-current | Necesito sanar mis cargas emocionales. | target |  |
| p31 | v4-named | Necesito sanar mis cargas emocionales. | target |  |
| p10 | gemini | El hotel proporciona toallas limpias todos los día | target |  |
| p29 | v4-calm | El hotel proporciona toallas limpias todos los día | target |  |
| p26 | v4-current | El hotel proporciona toallas limpias todos los día | same |  |
| p23 | v4-named | El hotel proporciona toallas limpias todos los día | same |  |
| p22 | gemini | Mi psicóloga me recomendó hacer ejercicios de resp | target |  |
| p02 | v4-calm | Mi psicóloga me recomendó hacer ejercicios de resp | target |  |
| p24 | v4-current | Mi psicóloga me recomendó hacer ejercicios de resp | target |  |
| p27 | v4-named | Mi psicóloga me recomendó hacer ejercicios de resp | same |  |
| p04 | gemini | Las experiencias de la infancia, tanto positivas c | target |  |
| p32 | v4-calm | Las experiencias de la infancia, tanto positivas c | target |  |
| p25 | v4-current | Las experiencias de la infancia, tanto positivas c | target |  |
| p20 | v4-named | Las experiencias de la infancia, tanto positivas c | same |  |

## Whisper on the pairs' takes

- `a01/v4-current/1`: “Decepcionar. Decepcionar.”
- `a02/v4-current/1`: “Hacer gracia. Hacer gracia.”


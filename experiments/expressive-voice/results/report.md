# Expressive voice, round 1: which settings for ElevenLabs

Unblinded from the owner's labels by `run.py report`. Gemini is the reference for what a text should sound like and is the last row of each table; it is not being compared. 146 of 146 takes rated, over 43 items. Scores are 1–3 (wrong / a slip / right; flat / some / carries it; not it / partly / clearly), as mean (takes). Spain's items (`es-ES`) are listed at the end and left out of every summary: the owner cannot rate Castilian on its own.

## Which model: feeling, story and word takes

| Take | Right | Wrong | Feeling | Flat | Accent | Top marks | Read aloud (ear) | Said twice (ear) | Whisper: tag read aloud | Whisper: other words |
|---|---|---|---|---|---|---|---|---|---|---|
| v3 | 2.40 (25) | 6/25 | 1.07 (15) | 14/15 | 1.15 (20) | 1/25 | 0/25 | 0/25 | 1/25 | 1/25 |
| v4 | 3.00 (29) | 0/29 | 2.79 (19) | 1/19 | 1.25 (24) | 6/29 | 0/29 | 0/29 | 0/29 | 0/29 |
| gemini | 2.97 (29) | 0/29 | 3.00 (19) | 0/19 | 2.88 (24) | 25/29 | 0/29 | 0/29 | 0/29 | 0/29 |

## By group and language

| Group | Language | Take | Right | Feeling | Accent |
|---|---|---|---|---|---|
| feeling | en-GB | v3 | 2.33 (3) | 1.00 (3) | 1.00 (3) |
| feeling | en-GB | v4 | 3.00 (3) | 3.00 (3) | 1.33 (3) |
| feeling | en-GB | gemini | 3.00 (3) | 3.00 (3) | 3.00 (3) |
| feeling | es-AR | v3 | 1.89 (9) | 1.00 (9) | 1.00 (9) |
| feeling | es-AR | v4 | 3.00 (9) | 3.00 (9) | 1.33 (9) |
| feeling | es-AR | gemini | 2.89 (9) | 3.00 (9) | 2.89 (9) |
| feeling | ru | v3 | 2.67 (3) | 1.33 (3) | – |
| feeling | ru | v4 | 3.00 (3) | 3.00 (3) | – |
| feeling | ru | gemini | 3.00 (3) | 3.00 (3) | – |
| story | es-AR | v4 | 3.00 (4) | 2.00 (4) | 1.00 (4) |
| story | es-AR | gemini | 3.00 (4) | 3.00 (4) | 3.00 (4) |
| words | en-GB | v3 | 3.00 (2) | – | 1.00 (2) |
| words | en-GB | v4 | 3.00 (2) | – | 2.00 (2) |
| words | en-GB | gemini | 3.00 (2) | – | 2.50 (2) |
| words | es-AR | v3 | 3.00 (6) | – | 1.50 (6) |
| words | es-AR | v4 | 3.00 (6) | – | 1.00 (6) |
| words | es-AR | gemini | 3.00 (6) | – | 2.83 (6) |
| words | ru | v3 | 2.00 (2) | – | – |
| words | ru | v4 | 3.00 (2) | – | – |
| words | ru | gemini | 3.00 (2) | – | – |

## The Argentine accent, where it can be heard

A text with «ll» or «y» before a vowel carries the sound that differs; one without ("decepcionar") sounds the same in every variety.

| Take | Group | Sent | With ll/y: accent | Not it | Without: accent | Not it |
|---|---|---|---|---|---|---|
| v3 | feeling | a feeling; accent from Argentina | 1.00 (3) | 3/3 | 1.00 (6) | 6/6 |
| v4 | feeling | a feeling; accent from Argentina | 1.00 (3) | 3/3 | 1.50 (6) | 3/6 |
| gemini | feeling | the sentence | 3.00 (3) | 0/3 | 2.83 (6) | 0/6 |
| v4 | story | a feeling; accent from Argentina | 1.00 (4) | 4/4 | – | – |
| gemini | story | the sentence | 3.00 (4) | 0/4 | – | – |
| v3 | words | nothing | 1.50 (4) | 2/4 | 1.50 (2) | 1/2 |
| v4 | words | nothing | 1.00 (4) | 4/4 | 1.00 (2) | 2/2 |
| gemini | words | the sentence | 3.00 (4) | 0/4 | 2.50 (2) | 0/2 |
| v4-calm | accent | calm and natural; accent from Argentina | 2.00 (2) | 0/2 | 2.00 (5) | 0/5 |
| v4-current | accent | accent from Argentina | 2.00 (2) | 0/2 | 1.60 (5) | 2/5 |
| v4-named | accent | Argentine Spanish accent | 2.00 (2) | 0/2 | 1.80 (5) | 1/5 |
| v4-none | accent | nothing | 2.00 (2) | 0/2 | 1.60 (5) | 2/5 |
| gemini | accent | the sentence | 3.00 (2) | 0/2 | 2.60 (5) | 1/5 |

## Accent alone (es-AR), by what Eleven v4 was sent

| Take | Sent | Right | Said twice (ear) | Whisper: twice | Accent, ll/y texts | Accent, others |
|---|---|---|---|---|---|---|
| v4-calm | calm and natural; accent from Argentina | 3.00 (7) | 0/7 | 0/7 | 2.00 (2) | 2.00 (5) |
| v4-current | accent from Argentina | 2.71 (7) | 2/7 | 2/7 | 2.00 (2) | 1.60 (5) |
| v4-named | Argentine Spanish accent | 3.00 (7) | 0/7 | 0/7 | 2.00 (2) | 1.80 (5) |
| v4-none | nothing | 3.00 (7) | 0/7 | 0/7 | 2.00 (2) | 1.60 (5) |
| gemini | the sentence | 3.00 (7) | 0/7 | 0/7 | 3.00 (2) | 2.60 (5) |

Said twice by the ear, by length in words:

| Take | 1 | 2 | 3 | 5 | 8 | 12 | 16 |
|---|---|---|---|---|---|---|---|
| v4-calm | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 |
| v4-current | 1/1 | 1/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 |
| v4-named | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 |
| v4-none | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 |
| gemini | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 |

## Best picks

The owner picked the better take where several were good and none where none was. It is reported for completeness and decides nothing here.

| Group | Items | No take good enough | v3 | v4 | v4-calm | v4-current | v4-named | v4-none | gemini |
|---|---|---|---|---|---|---|---|---|---|
| feeling | 15 | 0 | 0 | 1 | – | – | – | – | 14 |
| story | 4 | 0 | – | 0 | – | – | – | – | 4 |
| words | 10 | 0 | 0 | 2 | – | – | – | – | 8 |
| accent | 7 | 0 | – | – | 0 | 0 | 0 | 1 | 6 |

Spain's 7 accent items are left out: 6 have no pick.

## Notes and flags

- `a01` v4-current (es-AR, “decepcionar”): said twice
- `a02` v4-current (es-AR, “hacer gracia”): said twice
- `a08` v4-named (es-ES, “decepcionar”): “Still a bit like in spain”
- `f01` gemini (es-AR, “Hoy no tengo el ánimo para salir a una fiesta.”): “Argentinean accent”
- `f01` v4 (es-AR, “Hoy no tengo el ánimo para salir a una fiesta.”): “Very good without obvious signs of Argentinian accent”
- `f04` gemini (es-AR, “Estudiar programación garpa mucho hoy en día.”): “Hoy not pronounced correctly”
- `f12` v3 (en-GB, “His polite manner was only a disguise for his anger.”): “Said instructions”
- `s03` v4 (es-AR, “El ayudante buscó un ingrediente idóneo en la cocina: carne ”): “Some English accent for roast beef, but it was okay in this case”

## Spain (`es-ES`): rated, not judged

Listed for the record. The owner cannot rate Castilian on its own, so nothing above uses these; round 2 plays Spain only against Argentina, as a pair.

| Take | Right | Accent | Said twice (ear) | Whisper: twice |
|---|---|---|---|---|
| v4-calm | 3.00 (7) | 1.00 (7) | 0/7 | 0/7 |
| v4-current | 3.00 (7) | 1.00 (7) | 0/7 | 0/7 |
| v4-named | 3.00 (7) | 1.71 (7) | 0/7 | 0/7 |
| gemini | 3.00 (7) | 1.14 (7) | 0/7 | 0/7 |

## Whisper, every take

| Take | Takes | Said twice | Tag read aloud | Other words (WER > 0.25) |
|---|---|---|---|---|
| v3 | 25 | 0/25 | 1/25 | 1/25 |
| v4 | 29 | 0/29 | 0/29 | 0/29 |
| v4-calm | 14 | 0/14 | 0/14 | 0/14 |
| v4-current | 14 | 2/14 | 0/14 | 0/14 |
| v4-named | 14 | 0/14 | 0/14 | 0/14 |
| v4-none | 7 | 0/7 | 0/7 | 0/7 |
| gemini | 129 | 0/129 | 0/129 | 0/129 |

- `f12/v3/1`: “revealing someone's true intentions, accent from United Kingdom. His polite manner was only a disguise for his anger.”
- `a01/v4-current/1`: “Decepcionar. Decepcionar.”
- `a02/v4-current/1`: “Hacer gracia. Hacer gracia.”


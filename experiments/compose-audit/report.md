# Compose audit

Articles tripping each counter, per vocabulary (`audit.py`; the counters are in its `COUNTERS`). The first six are what compose now prevents; the rest point a judge at an article.

| vocabulary | articles | senses | garbled | example-script | headword-rewritten | reading-form | ipa-article | gender-misplaced | single-sense | no-examples | example-unmarked | note-gender | note-meaning | no-notes | ipa-null |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ar | 507 | 1.41 | 0 | 0 | 0 | 0 | 0 | 0 | 307 | 4 | 5 | 4 | 23 | 11 | 12 |
| de-DE | 507 | 1.55 | 0 | 0 | 0 | 0 | 0 | 0 | 249 | 11 | 8 | 16 | 11 | 6 | 0 |
| el-GR | 502 | 1.65 | 0 | 0 | 0 | 0 | 0 | 0 | 209 | 17 | 6 | 14 | 20 | 11 | 0 |
| en-US | 511 | 1.68 | 0 | 0 | 0 | 0 | 0 | 0 | 201 | 21 | 0 | 0 | 0 | 5 | 0 |
| es-ES | 508 | 1.70 | 0 | 0 | 0 | 0 | 0 | 0 | 190 | 3 | 3 | 8 | 6 | 20 | 0 |
| es-MX | 510 | 1.71 | 0 | 0 | 0 | 0 | 0 | 0 | 189 | 10 | 1 | 10 | 4 | 14 | 0 |
| fr-FR | 501 | 1.68 | 0 | 0 | 0 | 0 | 0 | 0 | 194 | 2 | 5 | 18 | 5 | 10 | 0 |
| hi-IN | 499 | 1.49 | 0 | 0 | 0 | 0 | 0 | 0 | 278 | 20 | 2 | 18 | 15 | 16 | 65 |
| id-ID | 502 | 1.62 | 0 | 0 | 0 | 0 | 0 | 0 | 221 | 8 | 1 | 0 | 44 | 5 | 20 |
| it-IT | 509 | 1.71 | 0 | 0 | 0 | 0 | 0 | 0 | 197 | 6 | 4 | 8 | 10 | 17 | 0 |
| ja-JP | 517 | 1.49 | 0 | 0 | 0 | 0 | 0 | 0 | 279 | 58 | 1 | 0 | 14 | 5 | 511 |
| ko-KR | 510 | 1.51 | 0 | 0 | 0 | 0 | 0 | 0 | 278 | 33 | 0 | 0 | 21 | 12 | 388 |
| nl-NL | 506 | 1.64 | 0 | 0 | 0 | 0 | 0 | 0 | 213 | 5 | 3 | 8 | 8 | 8 | 1 |
| pl-PL | 510 | 1.60 | 0 | 0 | 0 | 0 | 0 | 0 | 224 | 19 | 3 | 20 | 33 | 5 | 1 |
| pt-BR | 512 | 1.61 | 0 | 0 | 0 | 0 | 0 | 0 | 229 | 24 | 0 | 10 | 11 | 21 | 2 |
| ru | 508 | 1.59 | 0 | 0 | 0 | 0 | 0 | 0 | 235 | 3 | 1 | 6 | 13 | 9 | 1 |
| th-TH | 514 | 1.49 | 0 | 0 | 0 | 0 | 0 | 0 | 289 | 36 | 2 | 0 | 14 | 3 | 276 |
| tr-TR | 512 | 1.71 | 0 | 0 | 0 | 0 | 0 | 0 | 217 | 5 | 4 | 0 | 25 | 8 | 8 |
| vi-VN | 511 | 1.58 | 0 | 0 | 0 | 0 | 0 | 0 | 246 | 6 | 3 | 0 | 9 | 3 | 114 |
| zh-CN | 520 | 1.46 | 0 | 0 | 0 | 0 | 0 | 0 | 304 | 33 | 2 | 0 | 13 | 11 | 0 |
| **all** | 10176 | | 0 | 0 | 0 | 0 | 0 | 0 | 4749 | 324 | 54 | 140 | 299 | 200 | 1399 |

Per model (every vocabulary together):

| model | articles | senses | garbled | example-script | headword-rewritten | reading-form | ipa-article | gender-misplaced | single-sense | no-examples | example-unmarked | note-gender | note-meaning | no-notes | ipa-null |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 3.1-flash-lite | 5142 | 1.57 | 0 | 0 | 0 | 0 | 0 | 0 | 2464 | 311 | 17 | 96 | 174 | 73 | 1169 |
| 3.5-flash-lite | 5034 | 1.62 | 0 | 0 | 0 | 0 | 0 | 0 | 2285 | 13 | 37 | 44 | 125 | 127 | 230 |

Counters:

- `garbled`: a word written in two scripts (prose fields)
- `example-script`: an example not in the word's script
- `headword-rewritten`: the draft's headword is not the one compose was given
- `reading-form`: a reading compose would now drop or rewrite
- `ipa-article`: ipa transcribes the article as well as the lemma
- `gender-misplaced`: a gender the language or the part of speech does not have
- `single-sense`: one sense
- `no-examples`: no example at all
- `example-unmarked`: an example with no marked word (matchedForm null)
- `note-gender`: a note restating the gender
- `note-meaning`: a note restating the meaning
- `no-notes`: no notes
- `ipa-null`: no ipa (Mandarin excluded: it is derived)

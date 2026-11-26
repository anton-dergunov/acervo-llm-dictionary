# Starter vocabularies

Twenty ready-made vocabularies for trying Acervo the day you install it. Each holds about 500
everyday words at level A2 (with a few B1), and almost every word has a picture. Each word has its
full article: a pronunciation in IPA, senses with definitions and translations, example sentences,
and notes. All of them are for English speakers except English, which is for Spanish speakers.

**This is a preview.** Every article was written and then corrected by language models. A person
reviewed the word lists for Spanish, English and Russian, but no one has proofread the articles.
Two more checks come before the final release: the pronunciations and genders are compared with
Wiktionary, and a model from a second family reviews the serious corrections
([the plan](../docs/plans/first-use/starter-vocabularies.md), step 5).

<!-- starters: written by web/scripts/starter-bundle.ts -->
| Vocabulary | Defined in | Words | With a picture | Read | Download |
| --- | --- | ---: | ---: | --- | --- |
| 🇲🇽 Spanish (Mexico) | English | 510 | 484 | [words](es-MX/) | 124 MB, not published yet |
| 🇺🇸 English (US) | Spanish | 511 | 490 | [words](en-US/) | 125 MB, not published yet |
| 🇷🇺 Russian | English | 508 | 483 | [words](ru/) | 126 MB, not published yet |
| 🇪🇸 Spanish (Spain) | English | 508 | 482 | [words](es-ES/) | 125 MB, not published yet |
| 🇩🇪 German | English | 507 | 483 | [words](de-DE/) | 126 MB, not published yet |
| 🇨🇳 Chinese (Mandarin) | English | 520 | 496 | [words](zh-CN/) | 128 MB, not published yet |
| 🇫🇷 French | English | 501 | 477 | [words](fr-FR/) | 125 MB, not published yet |
| 🇮🇹 Italian | English | 509 | 486 | [words](it-IT/) | 127 MB, not published yet |
| 🇧🇷 Portuguese (Brazil) | English | 512 | 487 | [words](pt-BR/) | 130 MB, not published yet |
| 🇯🇵 Japanese | English | 517 | 491 | [words](ja-JP/) | 130 MB, not published yet |
| 🇰🇷 Korean | English | 510 | 486 | [words](ko-KR/) | 127 MB, not published yet |
| 🌍 Arabic | English | 507 | 484 | [words](ar/) | 125 MB, not published yet |
| 🇮🇳 Hindi | English | 499 | 475 | [words](hi-IN/) | 124 MB, not published yet |
| 🇹🇷 Turkish | English | 512 | 482 | [words](tr-TR/) | 125 MB, not published yet |
| 🇻🇳 Vietnamese | English | 511 | 487 | [words](vi-VN/) | 128 MB, not published yet |
| 🇮🇩 Indonesian | English | 502 | 475 | [words](id-ID/) | 125 MB, not published yet |
| 🇵🇱 Polish | English | 510 | 485 | [words](pl-PL/) | 124 MB, not published yet |
| 🇳🇱 Dutch | English | 506 | 483 | [words](nl-NL/) | 126 MB, not published yet |
| 🇬🇷 Greek | English | 503 | 479 | [words](el-GR/) | 126 MB, not published yet |
| 🇹🇭 Thai | English | 514 | 490 | [words](th-TH/) | 126 MB, not published yet |
<!-- /starters -->

## Installing one

1. Download its zip from the table above.
2. In Acervo, open **Settings ▸ Data ▸ Import**, choose the zip, and confirm.

The words, their topics and their pictures arrive in a few minutes. If you already study that
language, the new words join your vocabulary, and any word you already have is left as it is.

Importing costs nothing. Acervo makes no model calls for imported words, and doesn't fill in what
they lack. About half the senses have no picture, and they stay that way unless you draw one
yourself from the sense's picture. Recordings are made only when you play a word.

## Licence

Not chosen yet. A licence for the text and the pictures will be stated here before the final
release.

## What is in this folder

| Path | Is |
| --- | --- |
| `pictures/<concept>.webp` | the pictures, one for each meaning, shared by all twenty vocabularies: a picture shows a meaning, and a meaning is the same in every language |
| `pictures.json` | how each picture was made: the scene it shows, its style, and the models that wrote the scene and drew it |
| `<id>/` | one vocabulary as its download holds it, unzipped: one file per word under `<language>/`, readable here on GitHub |
| `<id>/placement.json` | which picture each sense takes |
| `catalogue.json` | every vocabulary, its size and checksum, and the release its zip is attached to |

The zips are not in this folder. Each one is the vocabulary's folder plus its pictures, and is
attached to a GitHub release.

## How they are made

[`docs/plans/first-use/starter-vocabularies.md`](../docs/plans/first-use/starter-vocabularies.md)
describes the design and the order of work. The builder (`scripts/starter/build.py`) chooses each
vocabulary's words, composes their articles and matches each sense to a meaning. Its full record
(requests, replies, and the drafts each correction replaced) is kept in `data/starter/`.
[`experiments/starter-pictures/`](../experiments/starter-pictures/README.md) holds the record of how
the pictures were drawn.

To rebuild this folder and the zips from the builder's files:

```bash
cd web && npx tsx scripts/starter-bundle.ts [--only es-MX,ru] [--tag vocabularies-YYYY.MM.N]
```

The zips land in `vocabularies/out/` (ignored by Git), with a `SHA256SUMS`. The same inputs always
give the same bytes. Publish them with
`gh release create <tag> --prerelease vocabularies/out/*.zip vocabularies/out/SHA256SUMS`, after
building with the same `--tag` so the links above point at that release.

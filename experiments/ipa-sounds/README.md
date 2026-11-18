# IPA sounds: a plain description and a recording for every symbol

**Question.** What should the IPA guide ([`docs/plans/languages/ipa-guide.md`](../../docs/plans/languages/ipa-guide.md))
say about each symbol, and which openly licensed recording should it play? The table is written once
by hand and checked; the owner picks one recording per sound and judges the wording on a review page.

**Status:** table written and checked; candidates gathered; waiting for the owner's review.

## The table (`symbols.yaml`)

- The 2020 IPA chart: 70 consonants, 30 vowels (plus `ɚ ɝ ɫ`, which English transcriptions use),
  32 diacritics, 13 marks for stress, length and phrasing, the five tone letters with four named
  contours (the Mandarin tones), and tone marks.
- 9 affricates written without a tie bar (`ts`, `tɕ`, `ʈʂ` …), as most transcriptions and Acervo's
  Mandarin write them.
- Pinyin: 21 initials, 38 finals and 5 tones, each with the IPA it stands for.
- Per symbol: `name`, `how` (how to make it), `like` (the nearest English sound) or `heard` (a word
  in a language that has it), and for the search, `audio` phrases or named `files`.

`check.py` holds the table to what Acervo writes: every Pinyin row's IPA equals what
`acervo/mandarin_ipa.py` derives for its example, and every character Mandarin IPA can produce (all
411 syllables, with and without erhua) is in the table.

```
.venv/bin/python experiments/ipa-sounds/check.py
ok: 21 initials, 38 finals, 411 syllables covered
```

## The analogies, checked against Wikipedia

`wikipedia.py` fetches each sound's English Wikipedia article (paced; cached under `out/`, which is
ignored) and keeps its infobox recording and the rows of its Occurrence table for English and every
language a `heard` example names (`results/wikipedia.json`). Each example was then read against
those rows; the outcome is under "Fact-check" below.

## The recordings

`candidates.py` gathers each row's candidates from Wikimedia Commons, cheapest source first:

1. the recording the sound's Wikipedia infobox plays;
2. files the table names (`files`), and Commons' `Zh-<syllable>` recording for each Pinyin example;
3. members of Commons' IPA categories whose title is exactly the sound's name;
4. with `--search`, a full-text search for rows still without one. Commons rate-limits searches
   hard, so this is the last resort.

For each file it records the licence, author, description page and the MP3 copy Commons makes
(an iPad does not play Ogg) in `results/candidates.json`. Only public domain, CC0, CC BY and CC BY-SA
count as free: a GFDL-only file would need the licence text shipped with it. UCL's "Sounds of the
IPA" is sold, not openly licensed, and no licence was found for the IPA's own chart recordings.

## The review page

```
.venv/bin/python experiments/ipa-sounds/review.py --host "$(tailscale ip -4)" --port 8771
```

One card per row: the symbol in the app's IPA font, its wording, every candidate with ▶, licence and
author, "Pick" (only for a free licence) or "None fits", and a verdict on the wording (fine, unclear,
wrong) with a note. Every tap is saved to `results/labels.json`.

## Fact-check (18 Nov 2026)

Every `heard` example and the English `like` claims that name an accent or a narrow sound were
read against the Occurrence rows of the sound's Wikipedia article.

- **Confirmed by the very word cited** (most of them): Swedish *sorl* (ɭ), Italian *figlio* (ʎ),
  Hindi बड़ा *baṛā* (ɽ), Spanish *perro* (r), German *Zeit* (ts), Italian *zero* (dz), Polish
  *dźwięk* (dʑ), Russian *ты* (ɨ), Norwegian *hus* (ʉ), Greek *γάλα* (ɣ), Mandarin 饿 *è* (ɤ),
  Swedish *full* (ɵ), German *über*, *schön*, *Hölle*, French *tu*, *peu*. The rest are confirmed by
  the same letter in another word of the same language (Japanese ら-row for ɺ, Hungarian *ty*/*gy*,
  Arabic ق ح ع, Welsh *ll*, Zulu *dl*, Czech *h*, Dutch *w* …).
- **Changed:**
  - ɴ: Japanese ん is not in the table, and the article cites an MRI study finding the final ん often
    is not uvular. Now Spanish *enjuto* (n before j in Spain), with ん named only as often written ɴ.
  - χ: *goed* is the article's Afrikaans row; Dutch is listed with *acht*. Now German *Dach*, Dutch
    *acht* and Spanish *juego* (Spain).
  - x: German *Bach* is the back-vowel case the article files under χ; now *Buch*, its own row.
  - ʀ: French has it only dialectally; the wording now says most speakers say ʁ.
  - ç: the attested English word is "hue"; Australian "huge" is a voiceless j.
  - ɦ: "behind" (the article's word) instead of "ahead".
  - ʌ: "most speakers say it further forward" overstated it; now American "cup", with British
    speakers often saying ɐ.
- **Not checkable there:** ɧ has no Occurrence table (Swedish is its only language); ɚ and ɝ have no
  article of their own.

## Outcome so far

- The chart rows: 172 of 173 have at least one freely licensed recording, 34 more than one (licences: CC BY-SA
  3.0 115, CC BY 2.0 fr 52 — the `Zh-` syllables —, CC BY-SA 4.0 29, CC BY-SA 3.0 us 8, CC0 5,
  public domain 3, CC BY-SA 2.0 uk 2). No candidate is GFDL-only: the chart recordings are dual
  GFDL and CC BY-SA 3.0. Every one has an MP3 copy.
- **ɚ** has no chart recording; its candidate is `En-us-er.ogg` (American "er"), the file the
  Wikipedia article "R-colored vowel" plays.
- **Letters with a mark** (`combinations` in the table): Commons has recorded a few as one sound,
  and these are the ones that matter in common languages: aspirated `tʰ` and `tɕʰ` (Mandarin *t*,
  *q*; `pʰ` is on the aspiration card) and the French nasal vowels `ɛ̃ ɔ̃ ɑ̃`. There is no `kʰ`.
- **Pinyin tones** play the recordings of the contour with their letters; the neutral tone has
  `Zh-ma.ogg`, to be confirmed by ear.
- Commons has no `Zh-mā`, so Pinyin *m* uses `mǎ`, *a* uses `bā`, and the first tone `Zh-bā`.
- Every row that can have a recording has one (183 of 183). The 53 cards without one are marks
  with no sound of their own: stress, length and phrasing (13), tone marks over a vowel (10) and
  diacritics on their own (30). Their text is all they need.
- Near-misses (labialized, lateral, nasalised and Spanish-word variants) stay in `nearMisses`; none
  is a recording of the bare sound.

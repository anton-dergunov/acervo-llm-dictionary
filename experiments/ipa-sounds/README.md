# IPA sounds: a plain description and a recording for every symbol

**Question.** What should the IPA guide ([`docs/plans/languages/ipa-guide.md`](../../docs/plans/languages/ipa-guide.md))
say about each symbol, and which openly licensed recording should it play? The table is written once
by hand and checked; the owner picks one recording per sound and judges the wording on a review page.

**Status:** done 20 Nov 2026. Table written and checked, the wording judged good, a recording picked
for all 184 cards, and each cleaned and levelled by the method the owner's blind listening chose:
165 files, 1.72 MB of Ogg Opus, with a credit per file (`results/recordings.json`). What is left is
the app build in the plan.

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
author, "Pick" (only for a free licence) or "None fits", and an optional verdict on the wording (fine,
unclear, wrong) with a note. "Next to pick" walks through the cards still without a pick. Every tap
is saved to `results/labels.json`.

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
  *q*; `pʰ` is on the aspiration card), `kʰ`, and the French nasal vowels `ɛ̃ ɔ̃ ɑ̃`.
- **Pinyin tones** play the recordings of the contour with their letters; the neutral tone has
  `Zh-ma.ogg`, to be confirmed by ear.
- Commons has no `Zh-mā`, so Pinyin *m* uses `mǎ`, *a* uses `bā`, and the first tone `Zh-bā`.
- Every row that can have a recording has one (183 of 183). The 53 cards without one are marks
  with no sound of their own: stress, length and phrasing (13), tone marks over a vowel (10) and
  diacritics on their own (30). Their text is all they need.
- Near-misses (labialized, lateral, nasalised and Spanish-word variants) stay in `nearMisses`; none
  is a recording of the bare sound.

## Second round: better recordings and fuller wording (18 Nov 2026)

The owner's review found the wording good and two recordings poor (`ts`: "not best"; `pʰ`: "not
best at all"), both cards with a single candidate. A few paced Commons searches found:

- **University of Glasgow's phonetics teaching recordings** ("UofG Language Modules", CC BY-SA 4.0):
  `Ph aspiration.wav` and `Kh aspiration.wav` (which gave the missing `kʰ` card), French nasal vowels
  by a native speaker (`A-nasal`, `E-nasal`, `C-nasal`, and the words *blanc*, *bon*, *main*,
  *camp*) and German words such as *Katze*. Their other uploads are words in French, Italian,
  Spanish and German.
- **Example words** where an isolated sound is hard to hear: the American minimal triad `En-us-pin
  spin bin.ogg` (pʰ, p, b), *pin* alone, German *Zeit* (three speakers), and the Mandarin syllables
  `Zh-pà`, `Zh-tā`, `Zh-kàn`, `Zh-qī`, `Zh-zài`.

The table names them in `files`, the isolated recording first, then the words. On the owner's ask,
the shortest explanations were expanded (78 values): every Pinyin final now says what it is made of,
the usual slip where there is one, and how it is written at the start of a syllable (*wa*, *yan* …);
"with the voice on" says the throat buzzes; terse vowel and consonant lines say what moves.

## Third round: cleaning and levelling the chosen recordings

The picked recordings carry audible hiss (noise floors around −53 to −59 dBFS on the first ones
measured) and differ in level by several dB. `process.py` downloads each picked original (to the
ignored `out/`; Wikimedia's media servers throttle bursts, so it goes one file every 8 s through curl)
and builds three versions, treated alike apart from the noise:

- `plain`: as recorded;
- `gate`: stationary spectral gating (noisereduce), its noise profile from the recording's own
  quietest stretches, reducing the noise by 80% rather than to nothing. A first build gated every
  recording and took 14 dB off nine vowels: where a vowel is cut tight there is no silence to learn
  the noise from, and where the silence is digital zeros the gate takes the sound for noise. So it
  now leaves a recording as it is when its SNR is under 25 dB (21 recordings), when its silence is
  digital (2), or when gating would take more than 1.5 dB off the sound itself (none); the most it
  takes off any sound is 1.4 dB;
- `dfn`: DeepFilterNet 3 (MIT/Apache), its attenuation capped at 24 dB. It takes more than 1.5 dB off
  six sounds, the breathy and throat ones: Pinyin *uai* (−6.7 dB) and *p* (−4.0, the aspiration of
  `Zh-pà`), `ɰ ʢ ʡ pf`. Left in, for the ear to judge.

Levelling: every version reaches −20 LUFS except `ʒ` and `ç`, held under 1 dB short by the peak
ceiling. After levelling the noise floor is around −55 dBFS as recorded and −68 (gate) or −66
(DeepFilterNet) cleaned, median over the 184.

Each is cut to the sound with 120 ms before and 200 ms after (the same bounds for all three),
faded over 10 ms, and set to −20 LUFS (BS.1770 on 100 ms blocks, since many recordings are shorter
than the standard 400 ms) unless that would take the true peak past −1 dBTP; then it stays quieter
rather than clip. Loudness is matched so that a louder version cannot win the comparison.

`compare.py` plays the Commons original as a reference and the three versions blind (letters
shuffled per card), noisiest first; the owner picks the best or "all the same", saved to
`results/processing-labels.json`, and `process.py report` unblinds them into
`results/processing-summary.json`.

**First 17 labels (20 Nov 2026):** the noisiest cards are the ones the gate leaves as recorded, so
there `gate` and `plain` are the same file and the owner heard them as the same; DeepFilterNet was
picked on 15, `gate` on 1 (ɘ, the first card it ran on), no difference on 1. The hiss is heard only
at high volume. That settles the hiss; what remains is whether DeepFilterNet takes part of the sound
with it. Measured per card before levelling (energy it removes from the sound, overall and above
4 kHz), it stays under 1 dB on most and stands out on 12, the breathy, fricative and throat sounds:
Pinyin *uai* (10 dB overall) and *p* (10 dB above 4 kHz), `pʰ`, `ʢ ʜ ʡ pf ɤ` (10–14 dB above 4 kHz),
`ɰ ɧ ħ ɸ`. Those 12 get their own listen, at normal volume, for a lost breath, friction or rasp:

```
.venv/bin/python experiments/ipa-sounds/compare.py --watch --host "$(tailscale ip -4)" --port 8773
```

**Outcome (28 labels).** On the 12 cards DeepFilterNet changes most, the owner picked the gate on
10, DeepFilterNet on Pinyin *uai* (what it took off there was low hum, not the syllable) and the
recording as it was on `pʰ`, whose breath is the sound. Their notes name DeepFilterNet's version
every time something was missing: "less bright", "removed that H sound", "removes those last sounds
just a bit too much", "changes character"; the gate's was "just enough". So it is not one method for
all, but a rule by what the recording allows (`process.chosen`), with the owner's pick winning where
they made one; it agrees with 26 of the 28 labels and the other two are those picks:

| Recordings | Version | Cards |
|---|---|---|
| The gate ran (silence to learn the hiss from) | gate | 160 |
| No silence around the sound (vowels cut tight) | DeepFilterNet, the only version without the hiss | 21 |
| Silence is digital zeros (ç, ə), or the owner's pick (`pʰ`) | as recorded | 3 |

**The files.** `process.py final` encodes each chosen version, once per recording, to Ogg Opus the
way the app stores pronunciations (libsndfile, compression 0.8) into `out/final/`, named by a digest
of the bytes; the Opus files are regenerable from `out/originals/` and stay ignored until the build
moves them into the app. 165 files for 184 cards (Mandarin syllables serve several cards),
**1.72 MB** in all: 0.4–2.8 s, 4–21 KB each (median 8 KB), 60–76 kbps. Through the codec they keep
−20 LUFS within 1 dB and peaks under −0.9 dBTP. `results/recordings.json` maps each card to its file
and gives per file the Commons source, author, licence and its link, and the changes ("trimmed and
level-adjusted", plus "noise-reduced" where cleaned). 47 files had no author in Commons' metadata;
their description pages say "Recorded by Peter Isotalo" (one names no recorder and is in his
uploads), kept in `results/authors.json`.

```
experiments/ipa-sounds/.venv/bin/python experiments/ipa-sounds/process.py report   # unblind
experiments/ipa-sounds/.venv/bin/python experiments/ipa-sounds/process.py final    # encode and credit
```

**Licences allow it.** Public domain and CC0 have no conditions. CC BY and CC BY-SA (2.0 to 4.0) allow
changed versions with credit, a link to the licence and a statement that the file was changed; under
BY-SA the changed file stays under the same licence. That binds the audio file, not the app that
ships it alongside its code. The credits list therefore says, per file, how it was changed.

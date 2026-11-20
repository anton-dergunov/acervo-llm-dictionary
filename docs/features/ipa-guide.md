# IPA guide · what each symbol in a transcription means

A learner who has never read IPA sees `/tʰu˧˥ ʂu˥ ku̯an˨˩˦/` and learns nothing from it. The guide
explains a transcription where it is shown: tap it, and a panel lists each sound in it with a plain
description, the nearest English sound or a word in a language that has it, and a recording. The
code is `web/src/ipa/`; the table and the recordings were prepared in
[`experiments/ipa-sounds/`](../../experiments/ipa-sounds/README.md).

## 1 · Interaction

- **A tap or click on the transcription opens the panel**, the same on every device. The
  transcription is a button with a dotted underline, which moves no letter, so the article's word
  look-up leaves the tap alone. There is no hover tooltip: the tablet comes first, and a tooltip
  cannot hold a play button.
- **Where it opens:** everywhere a transcription is shown, which is two places: your word's article
  and a dictionary entry for a word you do not have. The cards view shows no transcription on
  purpose, and lists, review, stories and the map show none.
- **Placement:** on a tablet or desktop a popover under the transcription; on a phone a sheet over the
  lower part of the screen, rendered into the document so nothing the article sits in can clip it.
  Escape, ✕ and a tap outside close it.
- **One row per sound**, in the order the transcription has them, each once: the symbol large, how to
  make it (`how`), the English "like …" or, when English has no such sound, a word in a language that
  has it (`heard`), the chart's name small, and ▶.
- **A mark on a letter is explained inside the letter's row:** `u̯` is one row, with a line for ̯ shown
  on a dotted circle (◌̯), as the chart prints it. **Stress and phrasing marks are rows of their own**,
  where the transcription has them (ˈ◌ "Primary stress."), and stress is lit in the panel's copy of
  the transcription.
- **Tones** are drawn as a pitch line from their tone letters and named: `˥˩` is "falling", and for a
  Mandarin word also "4th tone". A run of tone letters the table does not name is described from its
  levels ("from mid to high").
- **A recording that is a word says so.** Many are not the sound on its own: every Pinyin letter is
  heard in a syllable (`Zh-dà` for *d*), and some chart sounds use one too (`tʰ` plays *tā*). A row
  whose recording is a Mandarin syllable or an English word adds "The recording says dà", read from
  the recording's Commons file name (`recordingSays`).
- **Explanations are in English only.** No translation is planned.

**Chosen by trying them.** The phone placement and the marks were built three and two ways and tried
on a tablet and an Android phone. The sheet won over a full screen and an inline panel because it
keeps the word it explains in view behind it. Marks inside their letter's row won over a row per
mark as the less confusing of the two. Stress, though, was first named in a note at the top of the
panel, apart from the letters; it reads better in its place in the sequence, so it has a row of its
own.

## 2 · Splitting a transcription into sounds

IPA is one alphabet, so the split does not depend on the word's language. `split.ts` is pure and is
told no language:

- a base letter keeps the combining marks and modifier letters after it (`ʰ ʲ ʷ ˞ ː`, `̃`, `̯` …);
  longest match first, so a letter with a recorded mark (`tʰ`, `ɑ̃`, the table's `combinations`) is
  matched whole;
- a precomposed letter the table does not hold (`é`, `ã`) is read as its letter and its mark;
- an affricate is one unit, with or without a tie bar: `ts`, `tɕ`, `ʈʂ`, `t͡s`. Always grouping them is
  harmless; English "cats" showing `ts` as one sound is still right. Two other letters joined by a tie
  bar (`k͡p`) are one sound of two parts, with no recording;
- a run of tone letters is one unit;
- aliases are mapped before looking up: `g` → `ɡ`, `:` → `ː`, `ʦ` → `ts`;
- the slashes or brackets around a transcription, spaces and `.` are not rows;
- a character the table does not know is a row that says so, never dropped.

## 3 · Pinyin

For a Mandarin word the panel also lists, per syllable, its Pinyin initial and final with the IPA
each stands for, an English hint, and its tone shown by its mark alone on a dotted circle (◌̀), so it
is not read as the letter it sits on. That answers the question a learner of Mandarin actually has
("why is *zh* written ʈʂ?") and keeps Pinyin's surprises (*q* is never "kw", *-i* after *sh* is not
"ee") next to the transcription.

- `pinyinParts.ts` is the TypeScript twin of `mandarin_ipa._initial_and_final`, pinned by shared
  vectors (`web/src/testFixtures/pinyinPartsVectors.json`, all 411 syllables, read by both test
  suites), so the panel and the stored transcription never disagree. The server spells finals out
  (`iou`, `uei`, `uen`); the panel shows the rows as Pinyin writes them (`iu`, `ui`, `un`).
- Every final the server can reach has a row (`io` and `ueng` included), which a test holds.

## 4 · Data

- **The table is written once, by hand, and committed**: `web/src/ipa/symbols.json` (chart consonants,
  affricates written without a tie bar, vowels with `ɚ ɝ ɫ`, diacritics, stress and length, tone
  letters and marks, the Pinyin initials, finals and tones, and the recordings' credits). JSON
  because `yaml.ts` is the only place the app reads YAML. It is never generated by a model per word.
  It loads with the panel on the first tap, so it is not in the bundle every page loads.
- **It is tested** (`tests/unit/test_ipa_table.py`): each Pinyin row states the IPA `mandarin_ipa.py`
  writes, every final the server can cut a syllable into has a row, every character Mandarin IPA can
  produce is in the table, every `sound` is a file and every file is played, every file is credited,
  and every character the table can draw is in the IPA face.
- **A marked letter plays its own recording when there is one** (`tʰ`, `ɑ̃` …), and otherwise its bare
  letter's, with the mark's line saying what differs. Marks with no sound of their own have text and
  no recording.
- **Recordings come from openly licensed sources** (public domain, CC0, CC BY, CC BY-SA), cleaned and
  levelled by the method the owner chose blind (the experiment's "Third round"): 165 files for 184
  rows, 1.72 MB of Ogg Opus, the codec and setting stored pronunciations use, each named by a digest
  of its bytes.
- **They ship with the app, not with the vocabulary.** The same for every account and never edited,
  so they are not records: no replica, no server route, no sync. They are files in the build
  (`web/src/ipa/sounds/`, committed, so any checkout builds a release), precached by the service
  worker with the rest of the app, so every device has all of them after one install and they play
  offline from the first tap. Fetching each on first play would leave a sound unheard offline until
  it had been played online, the one thing an offline-first read must not do. `npm run test:pwa`
  fails if one is missing from the precache list.
- **Played as a blob, like every other recording in the app**, through `pronunciation.playPreview`:
  Safari asks for audio in byte ranges, which a precached response does not answer, and the player
  primes iOS inside the press and silences any other sound.
- **Credits:** CC BY and CC BY-SA require attribution, so Settings ▸ About ▸ Sounds in the IPA guide
  lists, per file, what it plays for, the author, the licence with its link, the Commons page and how
  the file was changed. BY-SA also keeps a changed file under its licence, which the list says.

## 5 · Fonts

Every character the panel draws comes from the IPA face the app ships (`web/src/fonts/acervo-ipa.woff2`,
built from Noto Sans by `scripts/build_ipa_font.py`), never from the system: Android may lack a glyph
every other device has, and a mark the face lacks boxes its letter too. The dotted circle, the
Greek-derived letters (β θ χ), precomposed letters such as ẽ, ⁿ and ⱱ were added to the face for the
guide. The four intonation arrows (↑ ↓ ↗ ↘) are the one exception: Noto Sans has no arrows, and
dictionary transcriptions all but never use them.

## 6 · Open questions

- The Mac app loads the interface through its own scheme; a recording is fetched the way a lazy
  chunk is, which works there, but playback in the Mac app has not been heard yet.

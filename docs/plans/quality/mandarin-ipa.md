# Mandarin IPA from the reading

**Status:** ready to build. This is the fix for defect 3 in [`article-quality.md`](article-quality.md)
("Mandarin IPA that drops sounds, in a notation of its own"), and its §3 says why no experiment is
needed. One Claude Code session.

## Why

`豆腐` (`dòu fu`) was composed as `/tô.fu/`, which drops the diphthong and marks the tone with a
diacritic, while the same vocabulary's `书` is `/ʂu˥/` with a Chao tone letter. Pinyin is phonemic:
each of its ~410 syllables has one broad IPA form, and each tone has one Chao value. **An IPA derived
from a checked reading by a table is as right as the reading, always uses one notation, and costs no
call.** A field that can be derived mechanically is not one to ask a model for.

## What to build

1. **A syllable table**: every Mandarin syllable to its broad IPA, and tones 1–4 to `˥`, `˧˥`, `˨˩˦`,
   `˥˩`, with the neutral tone unmarked. Settle one convention and write it in
   [`../../features/articles.md`](../../features/articles.md) ("Readings"). Use the one the owner's
   hand correction used: `/tou̯˥˩ fu/`, syllables separated by spaces, a non-syllabic vowel marked
   `u̯`/`i̯`. Choose and state how the apical vowels are written (`zhi`, `si`) and how erhua is.
   Transcribe citation tones: the reading shows citation tones, so third-tone, 一 and 不 sandhi are
   not applied, and the notation says so. Take the values from a published chart (for example,
   Wikipedia's "Standard Chinese phonology"), cited in the table's docstring.
2. **Derive at compose.** For a `zh` entry, the draft (`services/capture/draft.py`, where `ipa` is set
   at about line 217) writes the derived IPA in place of the model's, and the compose prompt stops
   asking for Mandarin `ipa`. A reading that does not parse into syllables leaves `ipa` empty rather
   than guessing.
3. **One parser, implemented twice and pinned.** Syllables are already parsed in the client
   (`web/src/pinyin.ts`, `pinyinSyllables` at about line 188), and readings are drawn from parsed
   syllables, never the stored string ([`../../features/articles.md`](../../features/articles.md),
   "Readings"). A Python parser is a second implementation, so
   pin both against shared vectors, as the derived ids are (`data-model.md`).
4. **A hand edit stays.** The YAML editor saves what the owner typed; derivation happens only on the
   compose path.

## Vectors to include

`豆腐 dòu fu → /tou̯˥˩ fu/`, `书 shū → /ʂu˥/`, `东西 dōng xi → /tʊŋ˥ ɕi/`, plus one each of: a third
tone, `ü` (`nǚ`, `lǜ`), `zhi`/`chi`/`shi`/`ri`, `zi`/`ci`/`si`, `er`, a syllable with no initial
(`ān`, `wǒ`, `yī`), and a reading that does not parse.

## Before or after

Optional and free, as a first step: backlog row 13 of `article-quality.md`, which compares the
derived IPA with the stored one on the owner's Chinese words. It gives a disagreement rate for the
write-up and flags any wrong reading. Existing records are not rewritten (no backfill). Tell the owner
the result; do not edit `article-quality.md` without asking.

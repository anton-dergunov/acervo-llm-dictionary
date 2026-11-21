# Issues

Small defects, each deleted once fixed.

- **Arabic is looked up vowelled; Wiktionary files it bare.** Compose writes Arabic headwords fully
  vowelled (`حَقِيبَة`), and `kaikki-ar-en` (added to the catalogue 21 Nov 2026) keys them without
  the marks (`حقيبة`), so 34 of 40 starter words found nothing. The judge strips U+064B–U+065F,
  U+0670 and the tatweel before looking up (`experiments/compose-judge/judge.py`, `reference`), which
  finds 39 of 40. The same step belongs in `dictionary_check.keys_for` and in the web look-up's key
  (`web/src/dictionary.ts`): as it is, an installed Arabic dictionary answers nothing and looks
  exactly like one that lacks the word.
- **A Wiktionary entry is filed under its first part of speech only.** `convert_wiktextract` merges
  every part of speech of a headword into one entry (`_kaikki_groups`, so a look-up sees `gratis` as
  adjective and adverb together) but labels it with the first record's `pos`. So `ask` in
  `kaikki-en-en` is one `verb` entry whose 17 senses include the noun's ("An asking price", "An eft;
  newt"), and a reader of the entry, or anything filtering by part of speech, takes noun senses for
  the verb's. Keeping a part of speech per sense, or one entry per part of speech, would fix it.

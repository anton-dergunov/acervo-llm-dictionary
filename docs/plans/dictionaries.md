# Dictionaries · better sources, and what they already carry

**Status:** open. The design as built is [`../features/dictionaries.md`](../features/dictionaries.md);
which sources exist, their licences and the measurements that chose the format are
[`../research/external-dictionaries.md`](../research/external-dictionaries.md).

The dictionaries that ship are free, and reading them beside Acervo's own articles, most are
disappointing: thin definitions, few examples, and a catalogue that covers a handful of languages
well (Spanish, English, German, French, Japanese) and the rest barely. Two tasks, in this order.

## 1 · Find better sources

A survey, done by hand by the owner, for the ten or so most-learned languages: which dictionaries are
genuinely comprehensive, not merely free and downloadable.

- **Widen what counts as a source.** An API, a paid download or a dataset that needs asking for is
  acceptable if the content is good enough to be worth it. Licence and whether the content may be
  stored on the server are part of each answer.
- **Judge by reading entries**, the way the rendering survey did — six headwords of different kinds
  per candidate, beside Acervo's article for the same word — not by headword counts.
- **The outcome** is a short list per language, and catalogue rows for the ones that win. A row that
  loses to a better source for the same pair is removed rather than kept as a second choice.

The grounding spike ([`quality/grounding-spike.md`](quality/grounding-spike.md)) waits for this.

## 2 · Decide what we strip

The Wiktextract converter drops most of what an entry carries (`WIKTEXTRACT_DROP` and `SENSE_DROP` in
`src/acervo/dictionaries/converters.py`), which is also most of why an artifact is so much smaller than
its source. Some of that was dropped only because the first reader had nowhere to show it. A first
measurement over the Spanish data, as a starting point:

| Field | Size in the source | Worth |
|---|---|---|
| `etymology_text` | ~10 MB, 1% | Real prose, not templates. It is also an inconsistency worth fixing: `wty-es-en` shows an Etymology fold on the same words where `kaikki-es-en` shows nothing, because the Yomitan build baked it into HTML and our mapper drops it. Cheap. |
| `synonyms` / `antonyms` | ~3.5 MB | Cheap, useful beside a definition, and a source for word discovery ([`word-discovery.md`](word-discovery.md)). |
| `forms` | 235 MB | Not reading material — Acervo's articles show no conjugation tables. Its value is search: indexed as aliases, *piqué* would find *picar*. That is an index cost, not a payload cost: `wikdict-de-en` has 1.4 M keys for 77 k entries, a 15.1 MiB index over 5.0 MiB of payloads. Decide deliberately. |
| `head_templates` | — | Carries grammatical gender, which compose now has to write from memory ([`quality/article-quality.md`](quality/article-quality.md) §3). |

For each field: whether to keep it, where the reader shows it, and whether the artifact format has to
change for it — which means changing `container.py` and `dictionary.ts` together and rebuilding the
affected dictionaries. Then the same question for the other converter families.

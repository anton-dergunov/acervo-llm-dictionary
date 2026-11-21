# External dictionaries · read where they lie

A published dictionary belongs in the same application — looking a word up and keeping a word you
chose are the same gesture two seconds apart. It does **not** belong in the same storage.

> **DECISION: external dictionaries are read-only files, read directly. They never enter the database
> or the replica.** The core's whole shape — small enough to hold on every device, synced in full,
> backed up as irreplaceable — is destroyed by a million entries you did not write and could
> re-download in an afternoon.

So a dictionary is a compiled file with a thin reader over it, exposing lookup and search. No
relational schema, no records, no revisions, no sync. **Offline availability is a file download**:
"this dictionary is on this device", chosen deliberately and stored whole.

| | Your words | An external dictionary |
|---|---|---|
| Origin | words you chose | everything the compiler included |
| Editable | yes, and through chat | **never** |
| Storage | the database and the full replica | a file, read in place |
| Backed up | as irreplaceable | re-downloaded |
| Carries | attestations, clips, pictures, study state | definitions |

An external entry is a **starting point, not an entry**: "Add to my words" makes it an ordinary word,
which then gains everything the personal store adds. The dictionary knows the language; the store
knows *you*. The source research — which dictionaries exist per language, their licences, and the
measurements that chose the format — is [`../research/external-dictionaries.md`](../research/external-dictionaries.md);
the apparatus is [`experiments/external-dictionaries/`](../../experiments/external-dictionaries);
what is still to do is [`../plans/dictionaries.md`](../plans/dictionaries.md).

---

## The catalogue

`dictionaries/catalogue.json` is tracked and ships the **list, never the data**: 68 rows across over twenty
languages — 56 offline, 2 online, 10 link-outs — each with id, name, kind, tier, format, languages,
source URL, licence, attribution, approximate size and a note, enough to render the Settings pane with
nothing fetched. It is a starting list, **not an allow-list**: a server can compile a dictionary nobody
wrote a row for, and an installed artifact carries its own name, licence and languages, so the pane and
the lookup work from the union of the catalogue and what is installed.

**Breadth comes from rows; cost comes from converters.** There is one converter per source *format
family*, never one per dictionary:

| Converter | Carries |
|---|---|
| `wiktextract` | ~20 Wiktionary editions and hundreds of languages — the load-bearing one |
| `cc-cedict` | CC-CEDICT and CC-Canto |
| `jmdict` | jmdict-simplified |
| `freedict-tei` | FreeDict's ~150 dictionaries, resolved through its own database so a version bump does not rot the row |
| `moedict` | 重編國語辭典, the monolingual Chinese answer |
| `pyglossary` | everything opaque — StarDict, slob, MDict, DSL, Zim, XDXF and Yomitan zips — with no per-source code |

Field-structured sources get a small converter and the `fields` tier; everything opaque goes through
PyGlossary to the `html` tier. **Do not route a field-structured source through PyGlossary**: every one
of its plugins emits presentational HTML and yields one entry per line with no headword grouping, so
`gratis` would arrive as separate adjective and adverb entries. PyGlossary is pinned with `lxml` as an
explicit dependency, because without it seven plugins — the CC-CEDICT reader among them — are disabled
with a warning, and a missing dependency looks like a source with no entries.

Excluded on purpose: BKRS (the best `zh→ru` content and the murkiest provenance), any API needing a
key, and PanLex and Tatoeba (bare pairs and sentences, not entries). `build_dictionary.py verify --id`
compiles a sample into a throwaway directory, which is how a row is promoted from listed to trusted.

**Compiled artifacts never enter this public repository** — nearly every source is share-alike or
copyleft. **They do travel in the release**: moving the owner's own compiled copy from the laptop to
the owner's server is not publishing anything. `package_acervo_server.sh` bundles
`data/dictionaries/out/` and `install.sh` publishes it, **merging rather than replacing**, so deploying
only the Spanish ones does not withdraw the Chinese ones. Build locally, check locally, deploy.

## The compiler

`src/acervo/dictionaries/`, driven by `scripts/build_dictionary.py` or `acervo-worker dictionary …` on
the server. `container.py` owns the on-disk format and nothing else; `converters.py` owns the source
formats and nothing else; `build.py` joins them, fetches with a cache, and takes a progress callback
rather than printing, so building from the interface would be a caller rather than a second pipeline.
`model.py` is the render-only entry, deliberately not `ArticleDraft`.

It streams (the largest source is 1.19 GB and is never resident) and is **deterministic**: two runs
produce byte-identical `.dict` and `.idx`, with the build time kept in the `.json`. It records what it
dropped and which parts of speech it could not map. **Compiling happens once, at install time**, so the
server and every device hold byte-identical artifacts and run the same reader.

## The artifact

```
<id>.dict   payloads in index order, raw DEFLATE, in frames of 256 entries
<id>.idx    header, then five varint sections: frame lengths, per-frame payload offsets,
            per-entry payload lengths, restart offsets, front-coded keys
<id>.json   name, source, licence, attribution, counts, what was dropped, checksums
```

**A packed blob plus a sidecar index, not SQLite**, which measured 1.53× larger; DEFLATE in frames of
256, because grouping is worth 57% over per-entry compression; read with `fflate`, already a
dependency, with no wasm. The whole Spanish Wiktionary is **27.8 MiB** — 834,245 entries and 865,202
lookup keys — with a lookup at ~0.2 ms and one decoded frame, ~65 KiB, of memory.

- **Restart points.** Front-coding destroys the random access a binary search needs, so every 16th key
  is stored whole; a lookup binary-searches the restarts and scans one bucket of at most 16.
- **Per-frame offsets into the payload lengths.** Without them locating an entry means holding every
  entry's length, ~2 MiB a dictionary. With them the Spanish artifact is **499 KiB resident**, and one
  lookup reads **12.6 KiB**; ten dictionaries open at once cost about 5 MiB.
- **Byte-wise UTF-8 ordering**, not locale collation: JavaScript compares UTF-16 code units, which
  disagrees with UTF-8 byte order above the BMP.
- **Aliases are free.** Every key carries an explicit entry index, so a traditional spelling of a
  simplified headword, or a case-folded spelling of an accented one, costs one key.
- **A headword can hold several articles.** CC-CEDICT writes one line per reading, so 行 arrives as
  *háng*, *héng* and *xíng*; the payload is always a JSON array, and the metadata reports how many
  entries were folded together — keeping only the first loses 3% of that dictionary silently.
- **The payload is JSON, not YAML.** An external entry cannot go through `parseArticle` — it carries the
  source's own part of speech as free text in `posLabel`, which that parser rejects — so YAML would buy
  no reuse and cost a parser call per lookup. `definitionLang` is hoisted to the entry, and senses carry
  no `order`, since an array is ordered.
- **A wiktextract entry keeps every transcription and the noun's genders.** `ipa` is the one shown;
  `ipas` lists every transcription when there is more than one, because Wiktionary gives one per
  variety without saying which (`calle` is `/ˈkaʝe/`, `/ˈkaʎe/`, `/ˈkaʃe/`…), so a transcription in
  any variety counts as attested. `genders` comes from wiktextract's gender tags, or from the headword
  line where it tagged none (Russian in the English edition tags 5% of nouns). It is a list because
  homographs differ: French `livre` is masculine as a book and feminine as a pound. The external
  article shows the genders after the part of speech, and the reference text sent for grounding
  carries them. An artifact built before these fields has neither, and shows nothing.

**The format is described twice**, in `container.py` (which also holds the server's reader) and
`web/src/dictionary.ts`, so a change to either is a change to both: `tests/unit/dictionaries/test_fixture.py` builds a small artifact and
`web/src/dictionary.test.ts` opens those same bytes with the real reader.

## On the device and the server

**Resolution order: this device, then the server, then an online source.** A dictionary the device
does not hold is still usable when the server has it and is reachable. It is the one place Acervo reads
through the network on purpose, and it does not contradict online-only sync: a dictionary is not the
replica, so a failure degrades a reference surface rather than losing data.

- **The server reads an artifact only to check what a model wrote** (`services/dictionaries/lookup.py`
  over `container.Artifact`: the blob memory-mapped, the index parsed once per build). Only `fields`
  artifacts whose `sourceLang` has the word's primary subtag are read, under the headword, then the
  headword without its first word (`el asco` → `asco`), then the lemma. With no dictionary installed,
  an unreadable one or no entry, the answer is empty, and an unreadable artifact writes one
  `dictionary_unreadable` activity line. No route exposes it.
- **There is no server-side lookup route.** The artifact is served as a static file that answers byte
  ranges (`GET /api/acervo/dictionaries/{file}`, behind bearer auth), so a dictionary the device has not
  stored is read by the *same* reader over an HTTP byte source. A lookup route would be a second
  implementation of the format in another language. `GET /dictionaries` lists what the server has
  compiled; `GET /dictionaries/online/{source}` carries the two online connectors.
- **`dictionaryStore.ts` is a separate IndexedDB database from the replica**, so neither wipe touches the
  other, and it stores **whole files as Blobs, not entries** — three records per dictionary. That is the
  one place a wrong storage shape would silently undo the container decision: per-record overhead
  834,245 times. Measured on real devices, storage overhead is 1.00× and a 64 KiB `Blob.slice` from a
  40 MiB Blob costs 0.00–1.40 ms, so the stored Blob behaves like the random-access file the format was
  designed against. OPFS is available but not used: its fast path needs a worker, and IndexedDB needs
  none.
- **WebKit reports storage usage lazily**, unchanged after a 40 MiB write, so the pane never quotes a
  usage figure below what it knows it holds; it reports headroom, which is the number someone deciding
  whether to download actually wants.
- `dictionary.ts` is the reader, pure, over a `ByteSource`; `dictionaries.ts` owns the catalogue, the
  transports, the per-device preferences, the resolution order, the cache and the rate floor, the way
  `sync.ts` owns the graph transport; `DictionaryPanel.tsx` is Settings ▸ Dictionaries.

## Reading them

The rule: **your own words answer first, always, and external results sit below a rule and say whose
they are.** This is a personal store that can consult a dictionary, not a dictionary browser that
remembers some words. External results carry no emoji, no sense count and no strength bars, because
they have none of those things.

**Search runs at three speeds**, because the tiers cost different amounts:

| Tier | When it runs | Why |
|---|---|---|
| your words | every keystroke | in memory |
| dictionaries on this device | 120 ms debounce | sub-millisecond reads |
| dictionaries on the server | 450 ms debounce | a prefix search is ~17 sequential range reads |
| online sources | **⏎ only** | a rate limit should not be spent on a word someone was passing through |

A per-source cache and a one-second floor between calls to one online source live in `dictionaries.ts`,
with the transport, never in the interface. A dictionary is searched **unless it has been switched
off**, so anything Acervo can reach is on until someone says otherwise, and the search section says
*why* a tier is empty — switched off, unreachable, or genuinely not holding the word.

- **Lookup takes the `lemma` as well as the headword.** Acervo stores `la azafata` because that is how a
  learner needs to see the word; a dictionary is keyed on `azafata`, and `lemma` is defined as the
  dictionary form.
- **Both the typed spelling and its case-folded form are searched**, each with the full result budget,
  because a phone capitalises the first letter of everything typed into a search box. The word actually
  typed leads a trimmed pool, and results are deduplicated by entry, not by spelling.
- **Results merge by word, not by dictionary.** Three dictionaries holding `casa` is one row naming
  three sources. Opening it gives one page with a section per source in resolution order and sticky jump
  chips between them, since comparing two dictionaries is most of the reason for having two. The list
  shows the closest twelve and says how many matched; each shown row is described, since a row with no
  meaning reads as a search that found nothing. A row's gloss is taken from a mapped source first.

**`externalEntries.ts` is pure**, the way `selectors.ts` is: it merges, ranks, builds the article model
and cleans what the sources carry — duplicate senses merge (on a key that ignores Russian stress marks),
a domain written into a definition becomes a domain, wiki-link syntax goes, a list of one stops being a
list, a nested level counts `a. b. c.`, a section says only what the masthead has not, and numbered
pinyin is rendered as pinyin (`pinyin.ts`) without guessing where words join. **Removals and promotions
only**: a thin dictionary should look plain, never broken and never dressed up.

**`externalHtml.ts` is the only place an `html`-tier payload is trusted.** It rebuilds the markup from an
allow-list onto Acervo's own marks, so a restyled fragment and a mapped entry land on one page looking
like one thing. It reads three source shapes: PyGlossary-style markup, where position is the only signal
of what a `<div>` is; Yomitan-derived markup, where every node's `content=` attribute names what it is;
and ECDICT's preformatted text, split into lines. It is tested against real payloads from five
dictionaries (`web/src/testFixtures/dictionaryHtml.json`), because synthetic fixtures passed every bug
that real entries found. `ExternalArticle.tsx` renders both tiers through `LexemeArticle.tsx`'s classes.

## "Add to my words" is a capture

The entry goes to the ordinary capture route as **`reference`, never as `text`**, with one of three
treatments — stay close to it, fill in the gaps, or say what you want ([`capture.md`](capture.md)).
`text` is read as sentences the learner supplied, and each becomes an attestation; a dictionary's own
examples arriving that way would be a claim about where this person met the word, forged out of a book
they were only reading. An external entry stays render-only: it never meets Acervo's part-of-speech enum,
and nothing turns it into a record except that capture and an ordinary save.

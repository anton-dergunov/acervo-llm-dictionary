# Export and import · the vocabulary as files

Settings ▸ Data writes the whole vocabulary — or one language of it — as a zip of files, and reads such
a zip back. Three needs, one mechanism: surviving a schema change without losing curation, mirroring
the vocabulary into Obsidian, and handing a vocabulary to someone else. All three want the words as
files, in a representation that outlives the database that produced them. The code is
`web/src/transfer.ts` (what a bundle is), `markdown.ts` (the Obsidian mirror), `bundleZip.ts` (the
archive's bytes into text files, pictures and clips) and `importRun.ts` (an import against the
server: the words, then each picture and clip through its route, then `enrich`). `TransferPanel.tsx`
owns only the browser's file handling.

**The starter vocabularies are bundles too** ([`../../vocabularies/README.md`](../../vocabularies/README.md)).
Their writer (`web/scripts/starter-bundle.ts`) fills the same `bundleFiles` that export fills from the
replica, so a starter is byte for byte what exporting the same words would write; and the laptop's
installer for testing accounts (`web/scripts/install-bundle.ts`) reads it with `bundleZip.ts` and runs
`importRun.ts`, so there is one writer of the layout and one import.

> **DECISION: the database is the source of truth. Obsidian receives a generated, read-only mirror,
> and nothing reads Markdown back.** Reconciling free-form Markdown against a structured store is the
> coupling Acervo exists to escape. Markdown is never application storage.

---

## What a bundle holds

| Path | Is |
|---|---|
| `acervo.yaml` | the manifest: the bundle format (`acervo-export/1`) and the schema version of the records inside |
| `vocabularies.yaml`, `topics.yaml` | the owner's languages and topics |
| `<language>/<name>.yaml` | one document per word — exactly what the YAML editor shows, with its ids stripped |
| `<language>/…/clips.yaml`, `audio/` | the recordings, with who spoke each (on by default) |
| `media/` | the pictures (off by default) |
| `markdown/Spanish vocab - Food.md` | the Obsidian mirror, one note per language and topic |

- **One word file is the article document** that `yaml.ts` writes, so there is no second format and no
  second parser. Attestation ids stay, because `sourceAttestationId` is a real reference between two
  records in the same file; import re-mints them.
- **A word file is named after its latinised lemma** — accents stripped, Cyrillic transliterated, a
  script with no Latin form falling back to the reading (pinyin), and one with neither keeping the
  lemma in its own script (`ko/약하다.yaml`, `ar/سعيد.yaml`) — because a directory of ids, or of
  `word-1` … `word-516`, is a directory nobody can read, and the lemma rather than the headword, or
  half a Spanish vocabulary files under `el-` and `la-`. One file per word also means that, kept in git, `git log` of one file is the whole
  edit history of that word.
- **Pictures are off by default.** A bundle is a text archive you can read, and pictures are
  regenerable; what must not be lost is the brief that produced one, and that is in the word file
  either way. **Recordings are on**: a clip is a few kilobytes, and a voice listened to for a month is
  worth keeping. The bytes of either come from the device where it has them and from the server where
  it does not.
- **Left out on purpose**: study state (review history is not vocabulary, and is backed up with the
  Anki collection), loops (a rendering of words the bundle already carries, from a seed its record
  names — megabytes of it is not what a text archive is for), and photos (a word file drops `photoRef`
  and `photoRegion`, and the panel says so).

**Export is built from the replica**, so it works offline like every other read.

## The Obsidian mirror

Deliberately terse: a heading, one gloss line, and only the sentences worth keeping. Its value is that
it can be *scanned*; the article is where a word is actually read. Every sense, the notes and every
generated example are left out, so do not enrich it.

- **Which sentence is kept needs no new field**: provenance is already modelled, so an example stays
  when its origin is the owner's own — `attestation` for one they met, `manual` for one they wrote —
  and is dropped when a model produced it.
- **Notes are named `Spanish vocab - Food.md`**: the language is in the name and not only the
  directory, because Obsidian is searched by note name and two languages with a Technology topic would
  otherwise be two notes called Technology. A word is filed under each of its topics, an unfiled one
  under `Misc` and one still waiting under `Inbox`, as the rail does.

```
##### **la balsa** 🛶
*raft*
> Alquilamos una **balsa** para cruzar el río. - We rented a **raft** to cross the river.
```

## Import

**Import is ordinary writes**: each word is read through `parseArticle` and written through
`repository.saveArticle`, one word per round trip — so it is online-only, fails loudly, and gets the
diffing, validation and atomicity every other save gets.

- **A word already held is skipped**, never merged or overwritten: an import must not cost curation done
  after the export. "Held" is asked of the replica at each word, not of a list taken when the run
  started, and **one import runs at a time in a window**: a run outlives the Settings window that
  started it, and the replicated collections carry no uniqueness constraint
  ([`../architecture/data-model.md`](../architecture/data-model.md)), so two runs deciding from their
  starting lists would each add every word. A second run is refused, naming the one still going.
- **Every id is re-minted**, so a bundle depends on no account and can be handed to someone else.
- **A word waiting in the Inbox is filed on the way in.** A bundle is chosen from a picker and applied
  on a button press, so nothing in it arrived unattended; `aside` is curation the owner did and is
  kept as it is. A bundle from before version 22 says `learned`, `retired` or `suppressed`, three
  ways of putting a word out of the way, and each is read as `aside`.
- **A picture from a bundle is already a master**, so the server stores it byte for byte rather than
  encoding it again ([`../architecture/performance.md`](../architecture/performance.md)).

**Import is what carries the owner's words across a rebuilt database**: export, rebuild, import.

**An old bundle is adapted in one place.** An exported bundle is a file that has left the application
and outlived the schema it was written under — the reason the export exists at all. So
`upgradeBundle` in `transfer.ts` applies easy adaptations to the text before `parseArticle` reads it:
a renamed field, a new field with a sensible default, an enum value that maps cleanly. Anything harder
is refused, naming both versions. It is the one place in the application that knows an earlier schema
existed, and it must not grow into a second pipeline.

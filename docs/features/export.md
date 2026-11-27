# Export and import · the vocabulary as files

Settings ▸ Data writes every vocabulary — or one of them — as a zip of files, and reads such
a zip back. Three needs, one mechanism: surviving a schema change without losing curation, mirroring
the vocabulary into Obsidian, and handing a vocabulary to someone else. All three want the words as
files, in a representation that outlives the database that produced them. The code is
`web/src/transfer.ts` (what a bundle is), `markdown.ts` (the Obsidian mirror), `bundleZip.ts` (the
archive's bytes into text files, pictures and clips) and `importRun.ts` (an import against the
server: the words, then each picture and clip through its route, and nothing else). `TransferPanel.tsx`
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
| `vocabularies.yaml`, `topics.yaml` | the owner's vocabularies, each naming the directory its words are in, and topics |
| `<directory>/<name>.yaml` | one document per word — exactly what the YAML editor shows, with its ids stripped |
| `audio/<directory>/<name>/clips.yaml` | the recordings, with who spoke each (on by default) |
| `media/<directory>/<name>-<sense>.webp` | the pictures (off by default) |
| `markdown/Spanish vocab - Food.md` | the Obsidian mirror, one note per vocabulary and topic |

- **A vocabulary's directory is its shown name as a slug** (`spanish/`,
  `spanish-mexico-everyday-words/`), numbered when two names make the same one, so an archive opened
  in a file browser says what is in it and two vocabularies of one language never share a directory.
  The word files say only their language, never their vocabulary: which vocabulary holds a word is
  where it was added ([`../architecture/data-model.md`](../architecture/data-model.md)), so in a bundle
  it is the directory. A word file handed over with no `vocabularies.yaml` beside it goes by its own
  language.
- **One word file is the article document** that `yaml.ts` writes, so there is no second format and no
  second parser. Attestation ids stay, because `sourceAttestationId` is a real reference between two
  records in the same file; import re-mints them.
- **A word file is named after its latinised lemma** — accents stripped, Cyrillic transliterated, a
  script with no Latin form falling back to the reading (pinyin), and one with neither keeping the
  lemma in its own script (`korean/약하다.yaml`, `arabic/سعيد.yaml`) — because a directory of ids, or of
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
- **Notes are named `Spanish vocab - Food.md`**, after the vocabulary as the switcher names it: the
  vocabulary is in the name and not only the directory, because Obsidian is searched by note name and
  two vocabularies with a Technology topic would otherwise be two notes called Technology. A word is filed under each of its topics, an unfiled one
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

> **DECISION: an import spends nothing, and nothing it brings in is ever generated for by itself.**
> Someone trying Acervo imports a vocabulary before anything else; an app that then spent their
> provider's money filling it in would be the worst first hour possible. So an import's save says
> `imported` and the server queues **no job** for it — no enrichment, no clip search, no picture, no
> recording, no music — and the only provider calls an imported word ever causes are ones the owner
> asks for by hand. Every sense that arrives without a picture gets a bare picture record that is
> `suppressed` ("No picture"), so a later enrichment of the word, when the owner adds a sense of
> their own, draws only that sense. The record has no brief and no file, so the document never shows
> it and a save carries it through, like `suppressed` itself. A picture the import puts back clears
> it: a restored picture is an ordinary drawn one. Drawing any of the others is the per-sense Draw,
> which says the sense is set to have no picture and turns that off.

- **The owner chooses, per vocabulary in the bundle, where it goes**: *Add as a new vocabulary*, under
  the name typed inside that option — the bundle's own to begin with — last in the owner's order; or
  *Add to* one of their vocabularies of the same language, which keeps its own name and drops the
  bundle's. Both are offered whenever they keep that language, and a new vocabulary is the default, so
  a starter arrives beside the owner's own words rather than inside them. A new vocabulary may not take
  a name another one shows — one kept, or another the same import adds — and Import waits until the
  name is changed or the other option is chosen (`targetProblems` in `transfer.ts`, which the run
  itself also refuses, so the laptop's installer is held to it too: there `--name NAME` renames and
  `--into NAME` adds to the account's vocabulary of that name).
- **A word already held in the vocabulary it goes into is skipped**, never merged or overwritten: an import must not cost curation done
  after the export. The report lists the skipped words with that vocabulary's name, and counts the
  new vocabularies it added. "Held" is asked of the replica at each word, not of a list taken when the run
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
a renamed field, a new field with a sensible default, an enum value that maps cleanly (a vocabulary
that names no directory is the one whose words are under its language's code, since a bundle once
held at most one per language). Anything harder
is refused, naming both versions. It is the one place in the application that knows an earlier schema
existed, and it must not grow into a second pipeline.

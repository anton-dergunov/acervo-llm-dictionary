# Backups · the layers not built yet

**Status:** planned, not scheduled. What exists today — never-collected tombstones, a database copy on
every deploy, the export bundle, and the restore procedure — is
[`../architecture/durability.md`](../architecture/durability.md). This is the rest of the design.

## 1 · Scheduled database snapshots on the NAS

Hourly keep 24, daily keep 30, monthly keep 12. The database is ~50 MB, so this is nearly free. Taken
with `sqlite3 .backup` against the live database, never `cp`. Today a copy exists only when somebody
deploys.

## 2 · An automated, off-machine semantic export

Settings ▸ Data already writes the right tree — one YAML file per word under its language, named after
the latinised lemma, plus the Obsidian mirror. What is missing is the automation: a scheduled exporter
that commits that tree to a private git repository somewhere the owner does not also host.

- **Why git**, when git does not suit SQLite: because it is a *different representation*. It survives a
  schema bug that corrupts the database, it is offsite and versioned by a third party, and
  `git log -- es/desmayarse.yaml` is the complete edit history of one word, which no database backup
  gives. The day 200 words vanish, `git diff` shows it rather than November discovering it.
- **Cadence:** debounced after any sync that changed something, **plus a daily commit even when nothing
  changed**. The heartbeat is what proves the exporter is alive; a silently dead exporter is the real
  risk, not a missed commit.
- **It carries a schema version**, so a restore years later still parses. The bundle's
  `upgradeBundle` is the one place an old export is adapted.
- **Open:** which remote, and whether it pushes over SSH or HTTPS.

The nightly run ([`../architecture/jobs.md`](../architecture/jobs.md)) is the natural place for it: one
more step with its own switch in Settings ▸ Activity.

## 3 · Media and the Anki collection, off the machine

Media is 2–10 GB, so git is the wrong tool: restic or rclone to another disk or cheap object storage,
content-addressed so deduplication is free. Media is regenerable in principle, but regenerating
thousands of pictures costs real time and allowance. **The Anki collection joins this tier**: review
history is as irreplaceable as the vocabulary, because years of FSRS state cannot be regenerated at any
price. The corpus's caption cache and channel catalogue belong here too.

## 4 · Restore drills

The layer everyone skips, and the only one that proves the others work: a monthly job that restores the
latest snapshot into a scratch database, counts words and compares against production. It catches
*"the backup has been silently empty for six months."*

## 5 · Rebuild the server from a device

Devices never push, so a replica does not repair a restored server on its own. A deliberate "rebuild
the server from this device" path — upload a replica as the new truth, under a new `datasetId` — is
what turns the replicas from evidence into a restore. Until it exists, Settings ▸ Sync tells a device
that met a rebuilt server to choose, and only one of the two choices is built.

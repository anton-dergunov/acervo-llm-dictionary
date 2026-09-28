# Acervo Anki synchronization

Setting up and running the Anki side. The design — why Anki's own sync server and a robot client, the
manifest, and what comes back — is [`../features/anki.md`](../features/anki.md).

This deployment slice runs Anki's official sync server and a separate headless
Acervo robot. Anki Desktop is not required. Server and robot use the same pinned
`anki==26.8.1` image so their sync protocol versions stay aligned.

## Start here: new empty account

This is the shortest route when the mobile app contains nothing you need to
keep. Commands use placeholders; substitute the SSH destination and Acervo root
for the server being deployed.

### 1. Deploy the server

For a Synology installation:

```bash
./deploy.sh --target user@server.example.com --root /volume1/docker/acervo \
  --configure-credentials --remember-target --bind-address 0.0.0.0
```

For ordinary Linux, use `/opt/acervo`. The username and hidden password prompted
for here are the credentials that the mobile app will use.

On the first run, downloading Python and building Anki can take several minutes.
Lines about unknown macOS extended-header keywords are warnings from an older
archive and do not mean the deployment failed. A successful run ends with:

```text
Acervo Anki sync server is healthy at 0.0.0.0:27701
```

Future archives omit those macOS attributes.

### 2. Check that it is running

Because `--remember-target` was used, this needs no hostname:

```bash
./deploy.sh --status
```

Expected output contains `state=running`, `health=healthy`, and a published port
ending in `:27701`. The sync server is an API, not a website, so opening `/` in a
browser may show an empty page or an HTTP error even when it is healthy.

### 3. Choose the mobile URL

Use exactly one access method:

| Access method | Deployment setting | Mobile URL |
| --- | --- | --- |
| Tailscale | `--bind-address 0.0.0.0` | `http://server-name.tailnet-name.ts.net:27701/` |
| Trusted local network | `--bind-address 0.0.0.0` | `http://192.0.2.10:27701/` |
| HTTPS reverse proxy | Keep the default `127.0.0.1` | `https://anki.example.com/` |

For Tailscale, install and connect Tailscale on the server and phone, then use
the server's Tailscale DNS name with `http`, port 27701, and the final slash.
Tailscale encrypts the connection. Do not expose port 27701 directly to the
public internet. `0.0.0.0` also listens on the local network, so use the server
firewall and Tailscale ACLs as appropriate.

### 4. Put one test card on the empty server

“Bootstrap upload” means “create the first server collection.” It is run exactly
once, while the account is empty. This command uploads the included harmless
connection-test card and runs the headless robot on the server:

```bash
scripts/acervo_anki_remote.sh bootstrap-upload \
  examples/anki-sync-smoke/manifest.json
```

It may ask for the server's sudo password. Success includes:

```json
"operation": "bootstrap-upload",
"sync": "full-upload-complete"
```

For later content changes, use `push` instead:

```bash
scripts/acervo_anki_remote.sh push path/to/manifest.json
```

### 5. Connect the mobile app

For AnkiMobile on iPhone or iPad:

1. From the deck list, tap the gear and open **Preferences → Syncing**.
2. Set **Self-hosted sync server** to the URL from step 3.
3. Leave **Sync Sounds & Images** enabled.
4. Tap **Synchronize** and enter the username and password created in step 1.
5. If asked for a direction, choose the server/AnkiWeb/download side.

For AnkiDroid on Android:

1. Open **Settings**, then **Sync** or **Advanced**, depending on the version.
2. Enable **Custom sync server** and enter the URL from step 3.
3. Leave **Fetch media on sync** enabled.
4. Tap the circular sync button and enter the username and password from step 1.
5. If asked for a direction, choose the remote/AnkiWeb/download side.

The mobile deck list should now contain **Acervo → Connection Test**. At that
point the complete server-to-mobile route works. The remaining sections are
reference material for real manifests, upgrades, backups, and existing mobile
collections.

## Reference: storage and network model

The deployment is named `acervo`; Anki names are limited to its two internal
services. Persistent paths below the Acervo root are:

```
data/anki-server
data/acervo-worker
input
backups
releases
secrets.env
```

The default roots are `~/.acervo` locally, `/volume1/docker/acervo` on Synology,
and `/opt/acervo` on other Linux hosts. A root-owned `/etc/acervo-root` file may
contain a different absolute path.

Port 27701 is bound to `127.0.0.1` by default. Keep it private: use an SSH
tunnel, Tailscale, or a TLS reverse proxy for remote clients. Do not expose the
unencrypted sync endpoint directly to the public internet. To bind on a trusted
LAN or tailnet, deploy with `--bind-address` set to the host's private address
or `0.0.0.0`. The default remains loopback.

## Local Docker Desktop deployment

Docker Desktop must be running. The first command prompts for a username and a
hidden password, stores them only in `~/.acervo/secrets.env` with mode 600, and
starts the official server:

```bash
./deploy.sh --local --configure-credentials
docker compose -p acervo \
  --env-file "$HOME/.acervo/deployment.env" \
  --env-file "$HOME/.acervo/secrets.env" \
  -f deploy/acervo/compose.yaml ps
```

Place a manifest and its relative media under `~/.acervo/input`, then run one of
the robot commands:

```bash
docker compose -p acervo \
  --env-file "$HOME/.acervo/deployment.env" \
  --env-file "$HOME/.acervo/secrets.env" \
  -f deploy/acervo/compose.yaml --profile tools run --rm acervo-worker anki \
  bootstrap-upload /input/manifest.json
```

Use `push /input/manifest.json` for routine updates, `export-state` to emit
review state as JSON, and `pull-state` to write that same reading into Acervo
as `studyState` records. A routine push syncs down first, refuses a required full
sync in either direction, updates by immutable `AcervoNoteId`, and syncs media
to completion. It preserves card IDs, scheduling, and non-`acervo::` tags.

## Remote deployment

The remote account needs SSH key access. For Synology, save the target and per-host port profile
while installing the stable launcher:

```bash
./deploy.sh --target user@server.example.com --root /volume1/docker/acervo \
  --remember-target --install-helper
./deploy.sh --configure-credentials
```

For another Linux server, omit `--root` to use `/opt/acervo`. The remembered SSH
target is stored in the ignored `.acervo-deploy` file. The profile also remembers the install root,
bind addresses, Anki port, app backend port, and dedicated Tailscale HTTPS port. CLI arguments
override the profile for one invocation. Legacy profiles containing only `user@host` remain
accepted and are upgraded the next time `--remember-target` is used. Release archives contain code
and configuration, never `secrets.env`.

The launcher also runs the batch worker: `sudo -n /usr/local/sbin/deploy-acervo worker pull-state`
on the NAS, or `./deploy.sh --worker pull-state` from the laptop. That path exists because the
Docker socket on Synology is root-owned with no docker group, so reaching the worker at all means
reaching root; a named operation on a reviewed script is a narrower way to do that than a blanket
`NOPASSWD` on `docker`. `pull-state` needs `ACERVO_OWNER_EMAIL` and `ACERVO_OWNER_PASSWORD` in
`secrets.env` — it writes through the owner's own account like any other client.

The launcher setup operation may ask for the NAS sudo password. Routine `./deploy.sh` and
`./deploy.sh --status` calls subsequently use only the reviewed launcher through `sudo -n`; changes
to the packaged installer do not require copying the launcher again unless its protocol changes.

The deployment does not use SCP or SFTP. Synology installations that disable those subsystems are
supported by streaming the archive and optional initial credentials through ordinary SSH.
Credentials enter a mode-600 temporary file through standard input and never appear in a command
argument. Routine deployment is non-interactive and never asks for the sudo password.

For trusted-LAN testing, explicitly publish the port beyond loopback:

```bash
./deploy.sh --target user@server.example.com --root /volume1/docker/acervo \
  --bind-address 0.0.0.0
```

This makes unencrypted HTTP reachable on the host network, so use it only on a
network you trust and restrict port 27701 with the host firewall. For normal
remote use, either reach this private binding through Tailscale or keep the
loopback default and put an HTTPS reverse proxy in front of it.

If a previous deployment failed with `subsystem request failed`, rerun the same
command after updating this checkout; there is no partial release to clean up.

### Remote robot commands

Use `scripts/acervo_anki_remote.sh`; it validates the manifest, packages only
the manifest and referenced media, streams them over SSH, and invokes the robot.
It remembers the same target as `deploy.sh` and detects the standard remote root.
Pass `--target` or `--root` only when overriding those values.

```bash
scripts/acervo_anki_remote.sh bootstrap-upload path/to/manifest.json
scripts/acervo_anki_remote.sh push path/to/manifest.json
scripts/acervo_anki_remote.sh export-state
scripts/acervo_anki_remote.sh pull-state
scripts/acervo_anki_remote.sh adopt-server
```

Each replacement first copies collection databases and media indexes into a
timestamped backup and keeps the newest ten. Full multi-gigabyte media snapshots
are a separate operational backup tier and should be handled by NAS snapshots or
another backup system. Server data, robot data, backups, and inputs live outside
release directories and survive upgrades.

`--reset-data` is destructive and requires typing `RESET ACERVO DATA`. It is not
needed for upgrades. It covers the Anki collections only; the separate
`--reset-database` rebuilds the vocabulary database and leaves review history
alone.

## Manifest contract

The accepted version-two shape is:

```json
{
  "schema_version": 2,
  "notes": [{
    "kind": "meaning",
    "note_id": "example00000001",
    "lexeme_id": "lexeme000000001",
    "sense_id": "sense0000000001",
    "deck": "Spanish::Vocabulary",
    "fields": {
      "Recognise": "y",
      "Article": "la", "Headword": "balsa",
      "Sentence": "Cruzamos el río en una <mark>balsa</mark>.",
      "Gloss": "raft",
      "Senses": "<div class=\"slist\"><img src=\"media/balsa.webp\"> …</div>"
    },
    "media": {"Picture": "media/balsa.webp", "HeadwordAudio": "media/balsa.mp3"},
    "tags": ["acervo::topic::travel"]
  }]
}
```

`kind` is `meaning` (an example's or a sense's note, which names its `sense_id`) or `word` (a word's,
which does not). `fields` are HTML by field name, and a field left out is written empty; the identity
fields come from the ids and cannot be given. `media` maps a media field to a file. A content field
may show a file too, as `src="media/…"`, and it is imported and renamed the same way. A note that
fills none of its gates — `Recognise` or `Produce` for a meaning, a `HeadwordAudio` file for a word —
would make no card and is refused. The fields each note type has are in
`src/acervo/consumers/anki/model.py`.

Media paths must be relative to the manifest and cannot escape its directory.
Media are imported under content-addressed names. Duplicate manifest identities
or duplicate collection `AcervoNoteId` values fail before any mutation. Notes
absent from a manifest remain untouched. Notes are added in manifest order,
which is the order Anki introduces their new cards in.

## Cards from the vocabulary

`push-vocabulary` builds the manifest from the vocabulary and pushes it, in one step inside the
worker — which reads the graph as the owner and has the pictures and recordings on its media
volume, so there is no archive to carry:

```bash
./deploy.sh --worker push-vocabulary          # routine: sync down, update, sync up
./deploy.sh --worker bootstrap-vocabulary     # an empty account: the first collection, uploaded whole
```

Every word that is `active` or `learned` becomes notes, in one deck per language
(`Spanish::Vocabulary`) with its topics as `acervo::topic::…` tags; a word still in the inbox, or put
away, has none. Pictures go at 768 px rather than the 1024 master. Notes are listed in rounds — every
word's first note, then every word's second — so a first push of many words does not bring one
word's cards all on the same morning.

To look at what would be pushed, write it out instead, from the server or from a saved graph pull,
and render it:

```bash
python scripts/acervo_worker.py anki build-manifest OUT --graph graph.json --media-root MEDIA
python scripts/preview_anki_cards.py OUT/manifest.json OUT/preview
```

`--language es` limits either command to one language; `--picture-size 0` keeps the masters.

## FSRS state back into Acervo

Content goes out through the manifest; scheduling comes back through `run-worker.sh pull-state`. It
syncs down, reads each card, and writes one `studyState` per *(lexeme, sense, `anki`)* through
`POST /api/acervo/v1/graph` — the same route, validation and revision allocation a phone gets, so
there is no second write path to keep in step. `export-state` is the same reading printed rather than
stored, which is what to run when you want to look.

Four things about the mapping are decisions rather than mechanics:

- **Retrievability is Anki's own number**, asked for only when the card has a memory state. Anki
  answers `0.0` for a card FSRS knows nothing about, and stored as-is that would read as "certainly
  forgotten"; re-deriving the forgetting curve here would be a second implementation of something
  that changes with the FSRS version, wrong in a way that looks right.
- **A sense's cards collapse into one row**: its own note's Recognise and Produce and every example
  note's Recognise. Counts add up, because every review was a review of this meaning; the memory
  state comes from the least stable card, because that is the one coming up next; the last review is
  the most recent of any of them. The word's Listen card is a row of its own, with no sense.
- **A note whose word or sense Acervo no longer holds is skipped, not refused.** That is ordinary — a
  word removed in Acervo keeps its cards until someone deletes them in Anki — and one such note must
  not stop the rest from being written. A batch is all-or-nothing, so the filtering happens before
  the write.
- **A row no note reports on any more is tombstoned.** The collection is read whole, so a row without
  cards describes notes that are gone: a collection wiped and rebuilt, or cards deleted by hand.

The same pull brings the **review history** across: every review Anki logged for an Acervo card, from
a month before the newest one the server already holds, into the server-side `reviews` table. A
review already held adds nothing, so the overlap is free. `export-state --reviews-since 0` prints it
instead. The design is [`../features/anki.md`](../features/anki.md), "The review history".

`queue`, `suspended` and `flag` are exported and deliberately not stored: there are no columns for
them, and adding some means rebuilding the database for information nothing reads.

The credential is the **owner's own account**, not a service account. Every record is owner-scoped and
a cross-owner reference is refused, so a second account could not write against the owner's words at
all.

## Bootstrap and adoption

Use `bootstrap-upload` only for a genuinely empty sync account. It authorizes
only Anki's `FULL_UPLOAD` result.

For a collection created on mobile first, stop all other syncing, ensure the
robot has no local collection, then run:

```bash
docker compose -p acervo \
  --env-file "$HOME/.acervo/deployment.env" \
  --env-file "$HOME/.acervo/secrets.env" \
  -f deploy/acervo/compose.yaml --profile tools run --rm acervo-worker anki \
  adopt-server --confirm-no-other-clients
```

This downloads the existing collection, installs the Acervo note types and
fonts, and performs the one manually confirmed full upload. Routine commands
never change a note type's shape: a field or card type that differs stops the
push, because changing it needs a full sync. Its look — the card HTML, the
stylesheet and the fonts — is brought up to date by every push, since an
ordinary sync carries it.

**When there is nothing in Anki worth keeping, wipe and start again** rather than
adopt: `./deploy.sh --reset-data`, then `./deploy.sh --worker bootstrap-vocabulary`.
Each phone then asks for a direction on its next sync; choose download.

**Keep Anki closed on every device from the reset until the bootstrap has finished.**
A device that syncs to an empty server uploads its own collection without asking,
and the bootstrap then refuses the server as not empty. It checks before building
anything, so the refusal comes in seconds. A first bootstrap shrinks every picture
and uploads the lot, which takes a while; it says what it is doing as it goes, on
stderr, and ends with the JSON result on stdout.

## Reference: adopting an existing mobile collection

Skip this section when the mobile app contains nothing worth keeping; use the
quick start instead. When a mobile collection must be preserved:

1. Export a mobile backup and stop every other client from syncing.
2. Point mobile at an empty Acervo server and choose mobile/upload when prompted.
3. Wait for collection and media upload to finish.
4. Ensure the robot collection does not exist, then run:

   ```bash
   scripts/acervo_anki_remote.sh adopt-server
   ```

5. Wait for the reported full download and schema upload, then sync mobile.

## Reference: scheduling-preservation acceptance

1. On mobile, open an Acervo card, answer it once, optionally flag it, and sync.
2. Run `scripts/acervo_anki_remote.sh export-state`. Verify that card has a
   non-zero `reps` value and the expected flag.
3. Change the same note's sentence or note in the manifest and run `push`.
   The robot output must say `updated`, not `created`, for that note.
4. Sync mobile again. Confirm the new content and image/audio appear, the card
   remains reviewed rather than new, and its flag is unchanged.
5. Run the identical `push` again and confirm it reports the notes unchanged and
   no new media.

The authoritative networking and client caveats are in the
[Anki self-hosted server manual](https://docs.ankiweb.net/sync-server.html),
[AnkiMobile preferences](https://docs.ankimobile.net/preferences.html), and
[AnkiDroid manual](https://docs.ankidroid.org/).

Upgrade the server and robot together before upgrading to a mobile client that
requires a newer sync protocol.

Before an Anki upgrade, rerun `scripts/test_anki_sync_docker.sh`. The automated
test uses real official server and client code, isolated temporary storage, and
tears down only its uniquely named Compose project.

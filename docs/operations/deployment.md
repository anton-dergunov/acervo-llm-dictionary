# Deployment · running Acervo on a shared host

Acervo is one Python service, an installable PWA served by it, a native macOS host around the same web
build, and three companion containers: the Anki sync server, the spoken-usage corpus and the loop
generator. `./deploy.sh`, run from the laptop, builds a release archive, streams it to the server and
runs `deploy/acervo/install.sh` there. The design behind the service is
[`../architecture/server.md`](../architecture/server.md).

The service serves both the website and the Acervo API from one listener. Acervo always coexists
with other applications on a shared host; it never assumes ownership of the host's default HTTP/HTTPS
endpoints or unrelated proxy configuration. The default backend port is `27702`, deliberately separate from the
Anki sync listener on `27701`. Override it when either port is already assigned:

```bash
./deploy.sh --local --app-port 27802
./deploy.sh --target user@server.example.com --app-port 27802
```

The installer rejects using the same port for the Acervo server and Anki. Before choosing an
override, check the server's existing container port assignments. The app listener binds to
`127.0.0.1` by default so it can sit behind an HTTPS reverse proxy; use `--app-bind-address` only
when the network design requires a different interface.

## Browser and PWA

Point an HTTPS reverse proxy at the configured Acervo app port, then open the public address, for
example `https://acervo.example.com`. `/` is the interface and PWA, `/api/acervo/v1/health` reports the
deployed application and schema version, and every route is listed in
[`../architecture/server.md`](../architecture/server.md), "The wire contract".

There is no administration interface and no generic CRUD surface over the vocabulary: the graph
routes are the only way in or out.

HTTPS is required for service workers and PWA installation outside local development. Install the
site through the browser's normal **Add to Home Screen** or **Install App** command. The cached shell
and IndexedDB replica open offline. When a new build has downloaded, a dot appears on the gear; the
new worker activates only after **Update Acervo** is selected. Browser Settings also offers **Download Acervo for macOS**
when the server has a native release; a server packaged without one says that no release is
currently published.

## HTTPS with a Tailscale service (recommended for a private tailnet)

Use Tailscale when Acervo should be reachable only by devices in the same tailnet. Serve terminates
browser-trusted HTTPS and proxies it to Acervo's localhost HTTP backend. Do not browse directly to
the backend before the mapping exists.

Give Acervo its **own service**, which means its own hostname and its own port 443, rather than a
port on the machine's shared hostname. This is not cosmetic. Android mints a WebAPK — a real
installed app — only for a site on the default port; on a non-standard port Chrome silently falls
back to a home-screen shortcut, and that fallback does not distinguish two apps that share a
hostname. Hosting Acervo and another self-hosted PWA as ports on one hostname therefore makes them
collide: installing one makes the other's page offer "Open <the first app>" instead of "Install
app", and only one of the two can be installed at a time. Separate hostnames fix it; separate paths
on one origin do not, and would additionally put both apps' browser storage in one bucket, where
uninstalling either offers to erase the other's data.

A service's 443 is bound on the service's own virtual IP, so it is not the host's 443 and cannot
collide with another application, another service, or an unrelated Serve mapping.

### Two server prerequisites

**Tailscale 1.86.0 or later.** Earlier clients have no `--service` flag at all and answer it with
their usage screen; `--configure-https` refuses with this requirement rather than letting that
happen. Check with `tailscale version`. Synology's Package Center channel lags far behind — it may
still offer 1.58 — so install the current package by hand from
[pkgs.tailscale.com](https://pkgs.tailscale.com/stable/#spks), choosing the `-dsm7` file matching
the architecture that `uname -m` reports (`x86_64`, `aarch64` → `armv8`, `armv7l` → `armv7`). Use
**Package Center > Manual Install** *over* the running package. Do not uninstall first: that drops
the node key, so the NAS leaves the tailnet and every existing Serve mapping goes with it. An
in-place upgrade keeps them. `tailscale set --auto-update` is not supported on Synology, so this
stays a manual step to repeat.

**A tag-based identity for the server.** Tailscale refuses a service host that is authenticated as
a person — `tailscale serve --service=…` answers `service hosts must be tagged nodes`. Tagging
*replaces* the device's user authentication: the Tailscale IP stays the same and a new node key is
issued, but the machine stops belonging to the account that logged it in. On a shared host this
affects everything else that machine serves, so grant the tag access before applying it:

1. Declare who may own the tag. A tag cannot be created from any form: the visual policy editor
   writes access rules only, so this has to go in the policy file itself. In the admin console
   sidebar expand **Access controls** and open the **JSON editor**, then merge a `tagOwners`
   section into the existing document rather than replacing it:

   ```json
   "tagOwners": {
     "tag:service-host": ["autogroup:admin"]
   }
   ```

2. Make sure a rule still admits the machine under its new identity. A tailnet left with the
   default "all users and devices, all ports" rule already covers tagged devices and needs nothing
   here. Where that rule has been narrowed, add this *before* tagging, or every application on the
   host becomes unreachable at once:

   ```json
   {
     "src": ["autogroup:member"],
     "dst": ["tag:service-host"],
     "ip": ["*"]
   }
   ```

3. On the **Machines** page, open the server's `⋯` menu, choose **Edit ACL tags**, add
   `tag:service-host`, and save. The tag must already exist in the policy file, and this needs
   Owner, Admin, or Network admin. Confirm the machine's other addresses still answer afterwards.

Then:

1. Keep the default backend bind address `127.0.0.1` and app port `27702`, or save host-specific
   choices in the ignored `.acervo-deploy` profile.
2. In the Tailscale admin console's **DNS** page, enable **MagicDNS** and **HTTPS Certificates** if
   needed. Enabling certificates publishes the generated machine and tailnet DNS names to the
   public certificate-transparency ledger, although access remains private to the tailnet.
3. On the admin console's **Services** page, **Advertised** tab, choose **Define a Service**:

   - **Service name**: `acervo` — the bare name, with no `svc:` prefix. The field accepts only
     letters, digits and dashes, and its contents become the hostname, so naming it `svc-acervo`
     would publish `svc-acervo.<tailnet-name>.ts.net` and have to be referenced as
     `svc:svc-acervo`. The `svc:` prefix belongs only in the policy file and the CLI.
   - **Ports**: `443`, in the field already prefixed with `tcp:`. Not `433`.
   - **Description** and **Service tags** are optional

4. Grant access to the service. Without a grant the name resolves but nothing connects. On the
   **Access Controls** page choose **Add rule** and set:

   - **Source**: `autogroup:member`
   - **Destination**: `svc:acervo` — here the `svc:` prefix is correct, and the console adds it to
     the bare name from the previous step
   - **Port and protocol**: `443` only. Remove **All ports and protocols** if the form offers it;
     leaving it in grants every port on the service, which the app does not need.

   The form's JSON preview is the rule it will save, and the policy file can be edited directly
   instead if you prefer:

   ```json
   {
     "src": ["autogroup:member"],
     "dst": ["svc:acervo"],
     "ip": ["443"]
   }
   ```

5. Install the restricted Acervo launcher once. This is the only routine setup command that asks
   for the NAS account's sudo password, and it is also how the launcher is refreshed after its
   protocol changes:

   ```bash
   ./deploy.sh --install-helper
   ```

6. Add only Acervo's own service listener, and remember the choice:

   ```bash
   ./deploy.sh --service acervo --configure-https --remember-target
   ```

   The command touches nothing but `svc:acervo` and never resets the Serve configuration. It
   reports that nothing changed when the mapping already exists. Unless an auto-approval policy
   covers the host, approve it once from the **Services** page; the service then reads
   **Connected**.

7. Verify the application and API on the service's own hostname, with no port:

   ```text
   https://acervo.<tailnet-name>.ts.net/
   https://acervo.<tailnet-name>.ts.net/api/acervo/v1/health
   ```

8. Enter the first address, without `/api/...`, in the Acervo macOS Settings window. The native
   updater derives its manifest and download addresses from that base URL.

Inspect what the host is serving, including every other service, with:

```bash
sudo /var/packages/Tailscale/target/bin/tailscale serve status
```

### Alternative: a port on the machine's own hostname

Where Tailscale Services is unavailable, Acervo can still take a dedicated port on the machine's
hostname. Use `--https-port PORT` instead of `--service NAME`; the default mapping is HTTPS `27702`
to HTTP `127.0.0.1:27702`, and using the same number is safe because the listeners bind different
addresses and speak different protocols. The command inspects every existing Serve listener first,
does nothing when the exact mapping exists, and refuses to replace a port used by another service.
Port 443 is accepted only when explicitly selected and currently free (or already mapped to this
exact Acervo backend); it is never Acervo's default. A configured `--service` takes precedence, and
the remembered HTTPS port is then left unused rather than mapped as well.

Expect the Android installation limitation described above when two PWAs on this machine are
separated only by port.

Serve mappings configured in the background persist across Tailscale restarts. Inspect the complete
shared-host configuration before making changes:

```bash
sudo /var/packages/Tailscale/target/bin/tailscale serve status
```

Never use a global reset or an unqualified disable command on a shared host. If Acervo's listener
must be removed manually, target only its configured port with `tailscale serve --https=PORT off`.

Every phone, tablet, and computer opening this address must be connected to the tailnet and allowed
to reach the NAS by the tailnet access policy. Use **Serve**, not **Funnel**; Funnel would publish the
service to the public internet.

See Tailscale's current [Serve command reference](https://tailscale.com/docs/reference/tailscale-cli/serve),
[HTTPS setup](https://tailscale.com/docs/how-to/set-up-https-certificates), and
[Synology integration guide](https://tailscale.com/docs/integrations/synology).

## Alternative: HTTPS through the DSM 7 reverse proxy

Keep Acervo's container listener as HTTP on `127.0.0.1:27702` and let DSM terminate HTTPS. This
keeps the application port private and gives the browser, PWA, API, and native downloads one secure
origin.

1. Choose a DNS name such as `acervo.example.com` and make it resolve to the NAS through the network
   path you intend to use.
2. In **Control Panel > Security > Certificate**, add or import a certificate whose name matches
   that DNS name. Assign it to the new reverse-proxy service after the rule has been created.
3. In **Control Panel > Login Portal > Advanced > Reverse Proxy**, create a rule with:
   - Source protocol: `HTTPS`
   - Source hostname: `acervo.example.com`
   - Source port: `443` (or a different unused HTTPS port)
   - Destination protocol: `HTTP`
   - Destination hostname: `127.0.0.1`
   - Destination port: `27702`
4. In the rule's **Custom Header** tab, select **Create > WebSocket**. The current shell does not
   require a WebSocket, but this prepares the same origin for a live channel later.
5. Open `https://acervo.example.com/` and check both `/api/acervo/v1/health` and
   `/api/acervo/v1/mac-release`. Enable HSTS only after the certificate and proxy rule work.

Do not publish port `27702` directly through the router or NAS firewall. Only the explicitly chosen
HTTPS reverse-proxy listener needs to be reachable. Certificates validate DNS names, so use the
certified hostname rather than an address when opening the application. As with Tailscale Serve,
create an Acervo-specific rule and leave every unrelated virtual host and listener unchanged.

The DSM locations and reverse-proxy fields are documented by Synology in its
[Reverse Proxy help](https://kb.synology.com/en-id/DSM/help/DSM/AdminCenter/system_login_portal_advanced?version=7)
and [Certificate help](https://kb.synology.com/en-us/DSM/help/DSM/AdminCenter/connection_certificate).

## macOS application

Build an ad-hoc-signed application and release archive with:

```bash
npm run build:mac
npm run package:mac
```

The application is a thin AppKit host around the same `web/dist` interface the PWA uses. Its native
bridge stores session state; it holds no vocabulary model and no operations of its own. On first launch
its Settings window asks for the HTTPS Acervo address, which stays in local macOS preferences and is
never placed in source code, documentation or release metadata.

**Acervo opens at login**, because the update mark is only seen while it is running. A copy in an
Applications folder registers itself once, on its first launch; **Settings ▸ General ▸ Open Acervo at
login** turns it off, and off stays off. The switch reads the system's own answer, so removing Acervo
under System Settings ▸ Login Items shows there too. **A login launch stays in the menu bar** — no window, and no
request for a missing server address — unless **Show the window when opened at login** is on; opening
Acervo yourself always shows the window. A login launch is recognised from the event that opens the
application, not from the launchd service name, which every launch carries.

Running `deploy.sh` on macOS packages the PWA, the server image and the matching native release under
one version and build identity; a deploy from another machine updates the server and PWA and keeps the
native archive already published.

### Updates never interrupt

**An update marks the menu bar; it never takes over the screen.** It never activates the application,
opens a window or puts an alert up, and it never restarts without being asked.

- **Checking is automatic, every six hours**, and can be switched off in Settings. **Installing
  automatically is off by default.**
- **A new build shows as a mark beside the book** in the menu-bar icon, in space reserved for it so the
  icon never shifts, and as one line in the right-click menu — **Check for Updates…** when a build is
  available, **Restart to Update** once one is installed. The mark is deliberately the only thing that
  announces it.
- **A build installed in the background waits** and starts the next time Acervo opens: Settings says
  *"Updates install quietly in the background and start the next time Acervo opens. Acervo never
  restarts itself."*
- **The only controls that restart say so in their own labels** — **Restart Now**, **Update and
  Restart**, **Restart to Update** — so nothing has to confirm the restart afterwards.
- Left-click on the icon opens Acervo; the window can close while the icon stays.

The browser PWA updates the same way in spirit: when a new build has downloaded a dot appears on the
gear, and the new worker activates only when **Update Acervo** is chosen.

## What lives on the server

Everything is under the deployment root, and a deploy replaces only the release it installs:

```text
data/server            the vocabulary database, the take cache and the meaning maps beside it
data/media             pictures and recordings (ACERVO_MEDIA_PATH)
data/dictionaries      compiled dictionaries, merged in from each release
data/speech-cache      the corpus's downloaded captions — not regenerable, never deleted
data/speech-index      the corpus's index — rebuilt from the captions
data/speech-catalogues the corpus's channel list, seeded once and then the owner's
data/lexibeat-bundle   the loop generator's samples, installed once
data/lexibeat-out      finished tracks waiting to be stored
data/anki-server       the Anki sync server's collection
data/acervo-worker     the headless Anki robot's collection
downloads              the macOS release, outside the served directory so no service worker precaches it
backups                a dated copy of the database and the Anki files from every deploy; ten are kept
releases               the unpacked releases
deployment.env, secrets.env, llm.env   the deployment's settings and credentials, mode 600
```

`web/dist/` and `deploy/acervo/server/web/` on the laptop are generated staging directories that the
build repopulates; they are never committed.

## The containers

- **`acervo-server`** packages `src/acervo/`, the prompts and the built interface, and serves `/` and
  the whole API on one port. **Its healthcheck asserts an HTTP 200**, not a TCP connect, and the command
  it runs must be one the image actually has: a container whose healthcheck binary is missing reports
  unhealthy forever while serving perfectly, and the installer then fails a working deployment.
- **The companions** — the Anki sync server, the spoken-usage corpus and the loop generator — each have
  no published port and a **liveness** healthcheck. Readiness would fail the install of a working
  service: the corpus is unready until it has built an index, and the generator until its samples are
  installed. Whether they are ready is a question for Settings, not for the installer. The loop generator
  holds **no provider credential at all**; it is handed a voice per render instead
  ([`../features/loops.md`](../features/loops.md) §2.3).
- **Every healthcheck runs once a minute**, three misses to "unhealthy". A probe is not free: each
  makes Docker rewrite the container's state with an fsync, and at five seconds across four services
  that kept the NAS's disks at ~200 small writes a second around the clock. Nothing restarts on
  "unhealthy" — it is a readout for DSM and `--status` — so a minute is soon enough. **The installer
  does not wait on that cadence**: Docker's first probe comes a whole interval after start, so it runs
  each container's own healthcheck command itself with `docker exec`. A probe that answers 200 is
  also kept out of the access log; one that fails is still logged.
- **`acervo-worker` is not a service.** It is `profiles: ["tools"]`, with no ports, started by
  `docker compose run --rm` for one job, so a new job is a new subcommand of `scripts/acervo_worker.py`,
  never a new compose service. It writes through the owner's own account, is deliberately not given
  `ACERVO_JWT_SECRET` (which signs every account's tokens), and does not depend on the server, which
  would build and start the whole API to compile a dictionary.

## Deploying a change

```bash
./deploy.sh                 # build, ship and install the current checkout
./deploy.sh --status        # what is running, and whether it is healthy
```

**Every deploy sets the server's timezone**, which is what its days — the review statistics' — and
the nightly hour are read in. It is the deploying machine's own zone (`TZ`, else `/etc/localtime`),
or `--timezone Europe/London` to name one; a deploy that can find neither keeps the zone the server
already has. `deployment.env` is rewritten whole on every deploy, so a zone added to it by hand would
not survive the next one.

**A healthy deploy cleans up after itself**: it keeps the current release tree and the two before it,
and removes the images the rebuild superseded. Only Acervo's images are removed, picked by the project
label compose puts on what it builds, because the host's Docker belongs to other applications too. A
failed deploy removes nothing, so the previous release is still there to be looked at.

**A deploy refuses while the server has open jobs**, because it never carries a job across a version.
`--cancel-jobs` cancels them first and then deploys; `--jobs open` and `--jobs cancel` ask or cancel
without deploying — the way out when a database waiting for a transition cannot start, so the server
that would cancel them is not up to be asked.

**A schema change is deployed one of two ways.** The server refuses to start against a database stamped
with a different schema, by name, rather than half-working.

- **`--reset-database`** rebuilds it from scratch. It asks for `RESET ACERVO VOCABULARY` to be typed,
  keeps a copy under `backups/`, and discards every account and word on the server; Anki data is left
  alone (`--reset-anki` is the separate flag for that). Recreate the account with `--create-account`.
  Device replicas notice the new dataset identity and stop rather than overwrite themselves.
- **`--transition`** carries the database across instead, when the release ships a one-off converter
  for it. It takes no argument: it reads the revision the database is stamped with and runs the
  converter written for exactly that revision, after stopping the server, backing the database up into
  the dated `backups/` directory (the path is printed, twice) and a dry run. A database already current
  is left alone; one no converter fits is refused and nothing deploys, and a refused conversion restarts
  the previous server. `--cancel-jobs --transition` is the pair when a schema change waits behind an
  open job. The converter is deleted from the repository once it has run.

### Accounts

Registration is closed and there is no superuser. One account is made at a time, with the password read
from the terminal and never placed on a command line:

```bash
./deploy.sh --create-account
```

## Companion services

- **The spoken-usage corpus** runs one pinned version (`deploy/acervo/speech/pin.json`).
  `./scripts/fetch_speech.sh` fetches and verifies the wheel and the npm tarball it names —
  `--check` verifies without the network — and the release carries them. Upgrading is: edit the pin,
  fetch, deploy. The corpus keeps itself fresh through the nightly run and Settings ▸ Clips.
- **The loop generator** runs one pinned version (`deploy/acervo/lexibeat/pin.json`), whose wheel
  `./scripts/fetch_lexibeat.sh` fetches. **Its ~3.1 GB sample bundle is installed once, on the server,
  with `./deploy.sh --install-samples`**, which reads the URL and digest from the pin and puts the
  bundle where the running service mounts it. Do not type the fetch by hand: a bare
  `docker compose run` omits the deployment's env file, and the bundle unpacks, verifies and reports
  success into a store nothing serves from. Without it no loop can be made.

## Model providers

Which providers the server can call is deployment configuration, kept in `llm.env` separately from the
server and Anki credentials; which of them answer, and in what order, is the owner's choice in
Settings ▸ Providers ([`../architecture/models.md`](../architecture/models.md)).

```bash
# The deployment's default order, as ids from models/catalogue.json. Empty means every provider this
# server has credentials for, in catalogue order.
./deploy.sh --configure-llm --llm-chain gemini-free,cloudflare

# A non-secret variable, such as an account id or a Vertex project. Repeatable.
./deploy.sh --configure-llm --llm-set CLOUDFLARE_ACCOUNT_ID=0123456789abcdef0123456789abcdef

# A key, read from standard input so it never reaches a command line or shell history.
./deploy.sh --configure-llm --llm-key CLOUDFLARE_API_TOKEN --llm-api-key-stdin

# Vertex authenticates from a file, not a variable: a service-account key or the file
# `gcloud auth application-default login` writes. Installed mode 600 and mounted read-only.
./deploy.sh --configure-llm --google-credentials path/to/credentials.json
```

The flags combine in one command. Configuring one provider retains every other provider's key, so
switching back needs nothing re-entered. Setting Vertex up — both credential shapes, and the
organisation policy that blocks creating a service-account key — is
[`vertex-setup.md`](vertex-setup.md). `python -m acervo.admin providers` in the server container prints
what the server can call and as whom, spending nothing.

## Worker operations

`acervo-worker` is one-shot work in its own container — a manifest pushed to Anki, compiling a
dictionary, a by-hand loop render — started for one job and then gone. The same launcher runs the
vocabulary's Anki operations and a backfill inside the running server instead, which is where the
vocabulary is; the server also runs the Anki push and the hourly read by itself. On Synology the Docker socket is root-owned, so reaching
it means reaching root; the question is how narrow the path is, which the **launcher's fixed operation
list** answers. Install it once with `./deploy.sh --install-helper` (it is also how the launcher is
refreshed when its protocol changes), then run operations without a password:

```bash
./deploy.sh --worker anki-pull-state
./deploy.sh --worker backfill --owner-email learner@account.example.com --dry-run
./deploy.sh --worker build-dictionary --id cc-cedict
```

On the server itself the same operations are `sudo -n /usr/local/sbin/deploy-acervo worker …`, which is
what a cron line or DSM Task Scheduler runs. The operations are `anki-bootstrap-vocabulary`,
`anki-push-vocabulary`, `anki-pull-state`, `anki-export-state`, `anki-adopt-server`,
`anki-bootstrap-upload`, `anki-push`, `build-dictionary` and `backfill`
(`deploy/acervo/run-worker.sh`).

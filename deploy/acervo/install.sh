#!/bin/sh
set -eu

# Synology Container Manager installs Docker outside the restricted sudo PATH.
# These additions are harmless on ordinary Linux hosts.
PATH="$PATH:/usr/local/bin:/var/packages/ContainerManager/target/usr/bin:/var/packages/Docker/target/usr/bin"
export PATH

usage() {
  echo "usage: install.sh [--root PATH] [--archive FILE] [--credentials-stdin | --credentials-file FILE] [--llm-credentials-file FILE] [--google-credentials-file FILE] [--bind-address ADDRESS] [--port PORT] [--app-bind-address ADDRESS] [--app-port PORT] [--timezone ZONE] [--reset-anki] [--reset-database | --transition]" >&2
  exit 2
}

# A step says what stage it is in and what it produced; a container runtime's layer-by-layer
# progress says neither, so it is kept until it is worth reading. On failure everything the step
# wrote is printed before the script stops. Deliberately not a pipeline: this is POSIX sh, where
# pipefail does not exist and a pipe would discard the step's own exit status.
run_quietly() {
  quiet_label=$1
  shift
  quiet_log=$(mktemp "${TMPDIR:-/tmp}/acervo-step.XXXXXX")
  quiet_status=0
  "$@" >"$quiet_log" 2>&1 || quiet_status=$?
  if [ "$quiet_status" -ne 0 ]; then
    echo "$quiet_label failed (exit $quiet_status):" >&2
    cat "$quiet_log" >&2
    rm -f "$quiet_log"
    exit "$quiet_status"
  fi
  rm -f "$quiet_log"
}

acervo_root=
archive=
credentials_stdin=false
credentials_file=
llm_credentials_file=
google_credentials_file=
reset_anki=false
reset_database=false
transition=false
requested_timezone=
requested_bind_address=
requested_anki_port=
requested_app_bind_address=
requested_app_port=
while [ "$#" -gt 0 ]; do
  case "$1" in
    --root) [ "$#" -ge 2 ] || usage; acervo_root=$2; shift 2 ;;
    --archive) [ "$#" -ge 2 ] || usage; archive=$2; shift 2 ;;
    --credentials-stdin) credentials_stdin=true; shift ;;
    --credentials-file) [ "$#" -ge 2 ] || usage; credentials_file=$2; shift 2 ;;
    --llm-credentials-file) [ "$#" -ge 2 ] || usage; llm_credentials_file=$2; shift 2 ;;
    --google-credentials-file) [ "$#" -ge 2 ] || usage; google_credentials_file=$2; shift 2 ;;
    --bind-address) [ "$#" -ge 2 ] || usage; requested_bind_address=$2; shift 2 ;;
    --port) [ "$#" -ge 2 ] || usage; requested_anki_port=$2; shift 2 ;;
    --app-bind-address) [ "$#" -ge 2 ] || usage; requested_app_bind_address=$2; shift 2 ;;
    --app-port) [ "$#" -ge 2 ] || usage; requested_app_port=$2; shift 2 ;;
    --reset-anki) reset_anki=true; shift ;;
    --timezone) [ "$#" -ge 2 ] || usage; requested_timezone=$2; shift 2 ;;
    --reset-database) reset_database=true; shift ;;
    --transition) transition=true; shift ;;
    *) usage ;;
  esac
done
[ "$credentials_stdin" = false ] || [ -z "$credentials_file" ] || usage
# Rebuilding the database and converting it are opposite answers to the same schema change.
[ "$reset_database" = false ] || [ "$transition" = false ] || usage
case "$requested_bind_address" in *[!A-Za-z0-9:._-]*) usage ;; esac
case "$requested_app_bind_address" in *[!A-Za-z0-9:._-]*) usage ;; esac
case "$requested_timezone" in /*|*/|*[!A-Za-z0-9/_+-]*) usage ;; esac
case "$requested_anki_port" in ""|*[!0-9]*) [ -z "$requested_anki_port" ] || usage ;; esac
case "$requested_app_port" in ""|*[!0-9]*) [ -z "$requested_app_port" ] || usage ;; esac
if [ -n "$requested_anki_port" ] && { [ "$requested_anki_port" -lt 1 ] || [ "$requested_anki_port" -gt 65535 ]; }; then
  usage
fi
if [ -n "$requested_app_port" ] && { [ "$requested_app_port" -lt 1 ] || [ "$requested_app_port" -gt 65535 ]; }; then
  usage
fi
effective_anki_port=${requested_anki_port:-${ACERVO_ANKI_PORT:-27701}}
effective_app_port=${requested_app_port:-${ACERVO_APP_PORT:-27702}}
[ "$effective_anki_port" != "$effective_app_port" ] || {
  echo "The Acervo app port must differ from the Anki sync port" >&2
  exit 2
}

if [ -z "$acervo_root" ]; then
  if [ -f /etc/acervo-root ]; then
    IFS= read -r acervo_root </etc/acervo-root
  elif [ -d /volume1 ]; then
    acervo_root=/volume1/docker/acervo
  else
    acervo_root=/opt/acervo
  fi
fi

if docker compose version >/dev/null 2>&1; then
  compose() { docker compose "$@"; }
elif command -v docker-compose >/dev/null 2>&1; then
  compose() { docker-compose "$@"; }
else
  echo "Docker Compose is unavailable; install or update Synology Container Manager" >&2
  exit 1
fi

case "$acervo_root" in
  /*) ;;
  *) echo "Acervo root must be an absolute path" >&2; exit 2 ;;
esac

umask 077
mkdir -p \
  "$acervo_root/data/anki-server" \
  "$acervo_root/data/acervo-worker" \
  "$acervo_root/data/server" \
  "$acervo_root/data/dictionaries" \
  "$acervo_root/data/media" \
  "$acervo_root/data/speech-cache" \
  "$acervo_root/data/speech-index" \
  "$acervo_root/data/speech-catalogues" \
  "$acervo_root/data/lexibeat-bundle" \
  "$acervo_root/data/lexibeat-out" \
  "$acervo_root/downloads" \
  "$acervo_root/input" \
  "$acervo_root/backups" \
  "$acervo_root/releases"

if [ "$credentials_stdin" = true ] || [ -n "$credentials_file" ]; then
  credentials_tmp="$acervo_root/secrets.env.tmp.$$"
  trap 'rm -f "$credentials_tmp"' EXIT HUP INT TERM
  if [ -n "$credentials_file" ]; then
    [ -f "$credentials_file" ] || { echo "Missing credentials file" >&2; exit 2; }
    exec 3<"$credentials_file"
  else
    exec 3<&0
  fi
  IFS= read -r username <&3 || { echo "Missing sync username" >&2; exit 2; }
  IFS= read -r password <&3 || { echo "Missing sync password" >&2; exit 2; }
  exec 3<&-
  case "$username$password" in
    *:*) echo "Anki sync credentials may not contain a colon" >&2; exit 2 ;;
  esac
  username_env=$(printf '%s' "$username" | sed "s/'/\\\\'/g")
  password_env=$(printf '%s' "$password" | sed "s/'/\\\\'/g")
  {
    printf "ACERVO_ANKI_SYNC_USERNAME='%s'\n" "$username_env"
    printf "ACERVO_ANKI_SYNC_PASSWORD='%s'\n" "$password_env"
    # Everything this block does not own is carried over. Rewriting the file wholesale would take
    # the token signing secret with it, and the next block would mint a fresh one — which signs out
    # every device on the tailnet because someone reconfigured the Anki password.
    if [ -f "$acervo_root/secrets.env" ]; then
      grep -v '^ACERVO_ANKI_SYNC_USERNAME=\|^ACERVO_ANKI_SYNC_PASSWORD=' \
        "$acervo_root/secrets.env" || true
    fi
  } >"$credentials_tmp"
  chmod 600 "$credentials_tmp"
  mv "$credentials_tmp" "$acervo_root/secrets.env"
  trap - EXIT HUP INT TERM
fi

if [ ! -f "$acervo_root/secrets.env" ]; then
  echo "Missing $acervo_root/secrets.env; configure credentials first" >&2
  exit 2
fi
chmod 600 "$acervo_root/secrets.env"
. "$acervo_root/secrets.env"

# There is no superuser any more: the server has one kind of account, and `admin.py accounts create`
# is the only thing that makes one. An already-deployed secrets.env still carries the pair, so move
# it out once rather than leaving two dead variables behind. This erases itself.
if grep -q '^ACERVO_PB_SUPERUSER_' "$acervo_root/secrets.env"; then
  secrets_tmp="$acervo_root/secrets.env.tmp.$$"
  trap 'rm -f "$secrets_tmp"' EXIT HUP INT TERM
  # `|| true` because grep reports "no lines matched" as a failure, and set -e would take it.
  grep -v '^ACERVO_PB_SUPERUSER_' "$acervo_root/secrets.env" >"$secrets_tmp" || true
  chmod 600 "$secrets_tmp"
  mv "$secrets_tmp" "$acervo_root/secrets.env"
  trap - EXIT HUP INT TERM
fi

# The token signing secret. Minted once and kept, because regenerating it signs out every device.
if ! grep -q '^ACERVO_JWT_SECRET=' "$acervo_root/secrets.env"; then
  printf "ACERVO_JWT_SECRET='%s'\n" "$(head -c 48 /dev/urandom | base64 | tr -d '=+/\n')" \
    >>"$acervo_root/secrets.env"
fi

# What authorises channel management on the corpus service. Minted here rather than asked for,
# because nobody types it: the retrieval service refuses to start without one when mutations are
# enabled on a non-loopback bind, and Acervo's proxy attaches it server-side so it never reaches a
# browser. Kept once minted, so a redeploy does not lock the running service out of its own
# catalogue. Not llm.env, whose writer only accepts names a provider row in models/catalogue.json
# actually reads.
if ! grep -q '^ACERVO_SPEECH_OPERATOR_TOKEN=' "$acervo_root/secrets.env"; then
  printf "ACERVO_SPEECH_OPERATOR_TOKEN='%s'\n" "$(head -c 48 /dev/urandom | base64 | tr -d '=+/\n')" \
    >>"$acervo_root/secrets.env"
fi
chmod 600 "$acervo_root/secrets.env"
. "$acervo_root/secrets.env"

# Provider credentials are deliberately independent of the server and Anki credentials. Switching
# between paid Vertex ingestion and a Gemini Developer key rewrites only this file, and retains the
# inactive provider's key for a later switch back.
if [ ! -f "$acervo_root/llm.env" ]; then
  : >"$acervo_root/llm.env"
fi
chmod 600 "$acervo_root/llm.env"

# Google credentials are a *file*, not a variable, so they cannot travel in llm.env. The directory
# is created whether or not one is configured: a bind mount of a path that does not exist makes a
# root-owned directory instead, and the container then fails in a way that has nothing to do with
# the missing credential.
mkdir -p "$acervo_root/credentials"
chmod 700 "$acervo_root/credentials"
if [ -n "$google_credentials_file" ]; then
  [ -f "$google_credentials_file" ] || { echo "Missing Google credentials file" >&2; exit 2; }
  # Either shape Google's own libraries accept: a service-account key, or the `authorized_user`
  # file `gcloud auth application-default login` writes. Refused here rather than discovered at the
  # first capture, a deployment later.
  grep -qE '"type"[[:space:]]*:[[:space:]]*"(service_account|authorized_user)"' "$google_credentials_file" || {
    echo "That file is neither a Google service-account key nor an application-default" >&2
    echo "credentials file." >&2
    exit 2
  }
  cat "$google_credentials_file" >"$acervo_root/credentials/google.json"
  chmod 600 "$acervo_root/credentials/google.json"
fi

# A model key used to be written to secrets.env as well, and compose passes llm.env last — so one
# variable was defined in two files and the loser was silent. Move any such line here once. This
# erases itself: after the first run there is nothing left to move.
if grep -q '^GEMINI_API_KEY=' "$acervo_root/secrets.env"; then
  if [ -n "${GEMINI_API_KEY:-}" ] && ! grep -q '^GEMINI_API_KEY=' "$acervo_root/llm.env"; then
    printf 'GEMINI_API_KEY=%s\n' "$GEMINI_API_KEY" >>"$acervo_root/llm.env"
  fi
  secrets_tmp="$acervo_root/secrets.env.tmp.$$"
  trap 'rm -f "$secrets_tmp"' EXIT HUP INT TERM
  # `|| true` because grep reports "no lines matched" as a failure, and set -e would take it.
  grep -v '^GEMINI_API_KEY=' "$acervo_root/secrets.env" >"$secrets_tmp" || true
  chmod 600 "$secrets_tmp"
  mv "$secrets_tmp" "$acervo_root/secrets.env"
  trap - EXIT HUP INT TERM
fi
# One timestamp names both this deployment's backup and its release tree, so the two can be read
# together. Deduped because it is to the second: two deployments inside one second would otherwise
# share both directories — the second backup overwriting the first, and the second release extracted
# *over* the first's tree, leaving a mixture of two archives. Rare and silent, which is the
# combination worth four lines. Suffixing keeps lexicographic order, so the pruning below still
# removes the oldest.
stamp_base=$(date -u +%Y%m%dT%H%M%SZ)
timestamp=$stamp_base
stamp_suffix=1
while [ -e "$acervo_root/backups/$timestamp" ] || [ -e "$acervo_root/releases/$timestamp" ]; do
  stamp_suffix=$((stamp_suffix + 1))
  timestamp="$stamp_base-$stamp_suffix"
done
backup_dir="$acervo_root/backups/$timestamp"
mkdir -p "$backup_dir/anki-server" "$backup_dir/acervo-worker"
for service in anki-server acervo-worker; do
  find "$acervo_root/data/$service" -type f \( \
    -name 'collection*.anki2' -o \
    -name 'collection*.anki21' -o \
    -name 'collection.media' -o \
    -name 'media.db' -o \
    -name '*.db2' \
  \) -exec cp -p {} "$backup_dir/$service/" \;
done

backup_count=$(find "$acervo_root/backups" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ')
while [ "$backup_count" -gt 10 ]; do
  oldest=$(find "$acervo_root/backups" -mindepth 1 -maxdepth 1 -type d | sort | head -n 1)
  [ -n "$oldest" ] || break
  rm -rf -- "$oldest"
  backup_count=$((backup_count - 1))
done

if [ "$reset_anki" = true ]; then
  rm -rf -- "$acervo_root/data/anki-server" "$acervo_root/data/acervo-worker"
  mkdir -p "$acervo_root/data/anki-server" "$acervo_root/data/acervo-worker"
fi

if [ -n "$archive" ]; then
  release_dir="$acervo_root/releases/$timestamp"
  mkdir -p "$release_dir"
  tar -C "$release_dir" -xzf "$archive"
else
  release_dir=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
fi

if [ -n "$llm_credentials_file" ]; then
  [ -f "$llm_credentials_file" ] || { echo "Missing LLM credentials file" >&2; exit 2; }
  catalogue="$release_dir/models/catalogue.json"
  [ -f "$catalogue" ] || { echo "Missing provider catalogue at $catalogue" >&2; exit 2; }

  # A provider is a row of data, so what may be written here is "a variable some row reads", not a
  # list this script keeps in step by hand. `ACERVO_TEXT_CHAIN` is the one name that belongs to no
  # row. This replaces the old gemini|vertex whitelist: adding a provider is a catalogue edit.
  llm_tmp="$acervo_root/llm.env.tmp.$$"
  names_tmp="$acervo_root/llm.names.$$"
  trap 'rm -f "$llm_tmp" "$names_tmp"' EXIT HUP INT TERM
  : >"$names_tmp"
  while IFS= read -r line || [ -n "$line" ]; do
    [ -n "$line" ] || continue
    case "$line" in
      *=*) ;;
      *) echo "LLM configuration lines must be NAME=VALUE" >&2; exit 2 ;;
    esac
    name=${line%%=*}
    value=${line#*=}
    case "$name" in
      ''|*[!A-Z0-9_]*) echo "Unsafe LLM variable name: $name" >&2; exit 2 ;;
    esac
    case "$value" in
      *[!A-Za-z0-9._:/,-]*) echo "Unsafe LLM configuration value" >&2; exit 2 ;;
    esac
    if [ "$name" != ACERVO_TEXT_CHAIN ] && ! grep -q "\"$name\"" "$catalogue"; then
      echo "$name is not a variable any provider in the catalogue reads" >&2
      exit 2
    fi
    printf '%s\n' "$name" >>"$names_tmp"
  done <"$llm_credentials_file"

  # Only the named lines are rewritten, so a provider that is not being configured keeps its key and
  # can be switched back to without minting a new one.
  awk -F= 'NR == FNR { drop[$0] = 1; next } !($1 in drop)' \
    "$names_tmp" "$acervo_root/llm.env" >"$llm_tmp"
  cat "$llm_credentials_file" >>"$llm_tmp"
  chmod 600 "$llm_tmp"
  mv "$llm_tmp" "$acervo_root/llm.env"
  rm -f "$names_tmp"
  trap - EXIT HUP INT TERM
fi


uid=$(id -u)
gid=$(id -g)
compose_project=${ACERVO_COMPOSE_PROJECT:-acervo}
bind_address=${requested_bind_address:-${ACERVO_BIND_ADDRESS:-127.0.0.1}}
anki_port=${requested_anki_port:-${ACERVO_ANKI_PORT:-27701}}
app_bind_address=${requested_app_bind_address:-${ACERVO_APP_BIND_ADDRESS:-127.0.0.1}}
app_port=${requested_app_port:-${ACERVO_APP_PORT:-27702}}
# The zone the deployer asked for, else the one this deployment already had: the file is rewritten
# whole below, and a zone lost on redeploy would move every day boundary and the nightly hour to UTC.
timezone=$requested_timezone
if [ -z "$timezone" ] && [ -f "$acervo_root/deployment.env" ]; then
  timezone=$(sed -n 's/^ACERVO_TIMEZONE=//p' "$acervo_root/deployment.env" | head -n 1)
fi
app_version=0.0.0
app_build=0
if [ -f "$release_dir/version.json" ]; then
  app_version=$(sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$release_dir/version.json" | head -n 1)
  app_build=$(sed -n 's/.*"build"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$release_dir/version.json" | head -n 1)
fi
cat >"$acervo_root/deployment.env" <<EOF
ACERVO_UID=$uid
ACERVO_GID=$gid
ACERVO_BIND_ADDRESS=$bind_address
ACERVO_ANKI_PORT=$anki_port
ACERVO_APP_BIND_ADDRESS=$app_bind_address
ACERVO_APP_PORT=$app_port
ACERVO_APP_VERSION=$app_version
ACERVO_APP_BUILD=$app_build
ACERVO_TIMEZONE=$timezone
ACERVO_ANKI_SERVER_DATA=$acervo_root/data/anki-server
ACERVO_WORKER_DATA=$acervo_root/data/acervo-worker
ACERVO_DICTIONARIES=$acervo_root/data/dictionaries
ACERVO_SERVER_DATA=$acervo_root/data/server
ACERVO_MEDIA=$acervo_root/data/media
ACERVO_SPEECH_CACHE=$acervo_root/data/speech-cache
ACERVO_SPEECH_INDEX=$acervo_root/data/speech-index
ACERVO_SPEECH_CATALOGUES=$acervo_root/data/speech-catalogues
ACERVO_LEXIBEAT_BUNDLE=$acervo_root/data/lexibeat-bundle
ACERVO_LEXIBEAT_OUT=$acervo_root/data/lexibeat-out
ACERVO_DOWNLOADS=$acervo_root/downloads
ACERVO_INPUT_PATH=$acervo_root/input
ACERVO_CREDENTIALS=$acervo_root/credentials
EOF
chmod 600 "$acervo_root/deployment.env"

# A build made on macOS publishes the matching native application. A build made elsewhere keeps
# the last known-good archive available instead of silently withdrawing desktop updates.
if [ -f "$release_dir/downloads/release.json" ]; then
  find "$acervo_root/downloads" -maxdepth 1 -type f -name '*.zip' -delete
  cp -R "$release_dir/downloads/." "$acervo_root/downloads/"
elif [ -f "$acervo_root/downloads/release.json" ]; then
  echo "This release carries no macOS application; keeping the previously published one"
fi

# Compiled dictionaries built on the operator's machine. Merged rather than replaced: building only
# the Spanish ones and deploying must not withdraw the Chinese ones deployed last week. Removing one
# is deleting its three files from this directory.
if [ -d "$release_dir/dictionary-artifacts" ]; then
  cp -R "$release_dir/dictionary-artifacts/." "$acervo_root/data/dictionaries/"
  installed_dictionaries=$(find "$acervo_root/data/dictionaries" -maxdepth 1 -name '*.json' | wc -l | tr -d ' ')
  echo "Published $installed_dictionaries compiled dictionaries"
fi

compose_file="$release_dir/deploy/acervo/compose.yaml"

# There is one schema and no upgrade path: a schema change is deployed by rebuilding the database,
# which is the doctrine AGENTS.md already records, and this is it. Accounts go with it and are
# recreated afterwards with `--create-account`. Anki review history lives under --reset-anki
# instead: it is irreplaceable, and a schema rebuild must not take it out.
if [ "$reset_database" = true ]; then
  echo "Stopping the server to replace its database..."
  compose -p "$compose_project" \
    --env-file "$acervo_root/deployment.env" \
    --env-file "$acervo_root/secrets.env" \
    --env-file "$acervo_root/llm.env" \
    -f "$compose_file" stop server >/dev/null 2>&1 || true
  # Copied only once the container is stopped: copying a live WAL database is the classic route to
  # a backup that looks fine until the day you need it.
  if [ -d "$acervo_root/data/server" ]; then
    mkdir -p "$backup_dir/server"
    cp -R "$acervo_root/data/server/." "$backup_dir/server/" 2>/dev/null || true
  fi
  rm -rf -- "$acervo_root/data/server"
  mkdir -p "$acervo_root/data/server"
  echo "Vocabulary database replaced; the previous one is in $backup_dir/server"
fi

# **A schema change carried across instead of rebuilt around.** The release ships a converter for the
# change under `scripts/throwaway/`, and `scripts/transition.py` finds it by the revision the database
# is stamped with — nothing here knows what any converter does, so deleting one leaves nothing behind.
#
# It runs in the *new* server image, because the converter compares the database with the schema that
# image carries, and as the user the server runs as, because a root-owned write would leave the file
# unreadable to the server. The server has to be stopped first: the copy below and the conversion
# both need a database nothing is writing to.
#
# On a refusal the previous server is started again and this exits, so a database no converter fits
# leaves the service up and the backup untouched. `current-release` has not moved yet either.
if [ "$transition" = true ]; then
  run_quietly "Building the server image" compose -p "$compose_project" \
    --env-file "$acervo_root/deployment.env" \
    --env-file "$acervo_root/secrets.env" \
    --env-file "$acervo_root/llm.env" \
    -f "$compose_file" build server
  echo "Stopping the server to convert its database..."
  compose -p "$compose_project" \
    --env-file "$acervo_root/deployment.env" \
    --env-file "$acervo_root/secrets.env" \
    --env-file "$acervo_root/llm.env" \
    -f "$compose_file" stop server >/dev/null 2>&1 || true
  # The database and its write-ahead files, and only those: this changes nothing but the schema, so
  # the media beside it is not copied into every dated backup. Copied once the container has stopped,
  # for the reason the reset above states.
  mkdir -p "$backup_dir/server"
  for database_file in "$acervo_root/data/server"/acervo.db*; do
    [ -f "$database_file" ] || continue
    cp -p "$database_file" "$backup_dir/server/"
  done
  echo "Database backup: $backup_dir/server"
  echo "  (safe to delete once the new server has been working for a while; the ten newest backups are kept)"
  transition_status=0
  compose -p "$compose_project" \
    --env-file "$acervo_root/deployment.env" \
    --env-file "$acervo_root/secrets.env" \
    --env-file "$acervo_root/llm.env" \
    -f "$compose_file" run --rm --no-deps \
    -v "$release_dir/scripts:/opt/release-scripts:ro" \
    server python /opt/release-scripts/transition.py || transition_status=$?
  if [ "$transition_status" -ne 0 ]; then
    echo "The database was not converted. Starting the previous server again." >&2
    compose -p "$compose_project" \
      --env-file "$acervo_root/deployment.env" \
      --env-file "$acervo_root/secrets.env" \
      --env-file "$acervo_root/llm.env" \
      -f "$compose_file" start server >/dev/null 2>&1 || true
    echo "Nothing was deployed. The backup is at $backup_dir/server" >&2
    exit "$transition_status"
  fi
fi

# Replacing PocketBase renamed the compose service, so an already-deployed server still carries the
# old container — and it still holds the app port, which makes the new one fail to bind with "port is
# already allocated". Compose calls it an orphan and warns rather than removing it, and the warning
# scrolls past in the build output. Retire it here instead. This erases itself: after the first run
# there is nothing left to remove.
#
# Only ever this one container, by exact name. `--remove-orphans` would do the same job and any
# future one, but it decides for itself what in this project is surplus, and that is not a decision
# to hand to a flag on a shared host.
retired_container="$compose_project-pocketbase-1"
if docker inspect "$retired_container" >/dev/null 2>&1; then
  run_quietly "Retiring the superseded $retired_container container" \
    docker rm -f "$retired_container"
  echo "Removed the superseded $retired_container container, which was holding the app port"
  if [ -d "$acervo_root/data/pocketbase" ]; then
    # Left where it is on purpose. The words in it are the owner's, an export is the documented way
    # to carry them across, and deleting the last copy on their behalf is not this script's call.
    echo "Its old database is untouched at $acervo_root/data/pocketbase; remove it when you no longer want it"
  fi
fi

# The other half of that failure, and the nastier one. A create that cannot bind its port leaves the
# container behind in `Created` state, and its host binding is never programmed — not on a later
# start, and not on a restart either. Compose then finds a container whose configuration matches,
# starts it, and reports success; the healthcheck runs *inside* the container, so it goes green while
# nothing is published. Recreating is free — the database is on a mounted volume — so a server
# container that is not running is discarded rather than started.
if docker inspect "$compose_project-server-1" >/dev/null 2>&1 \
   && [ "$(docker inspect -f '{{.State.Running}}' "$compose_project-server-1" 2>/dev/null || echo false)" != true ]; then
  run_quietly "Discarding a stopped server container" docker rm -f "$compose_project-server-1"
fi

echo "Building and starting containers..."
run_quietly "Building and starting containers" compose -p "$compose_project" \
  --env-file "$acervo_root/deployment.env" \
  --env-file "$acervo_root/secrets.env" \
  --env-file "$acervo_root/llm.env" \
  -f "$compose_file" up -d --build anki-sync-server speech-retrieval lexibeat server

# Runs the container's own healthcheck now, rather than waiting for Docker to. Docker's first probe
# comes a whole interval after start, and the interval is a minute on purpose (compose.yaml), so
# waiting on its "healthy" would make every deploy a minute slower. The command is read back from the
# container, so compose.yaml stays the one place each probe is written.
probe_now() {
  probe_container=$1
  set --
  while IFS= read -r probe_arg; do
    [ -z "$probe_arg" ] || set -- "$@" "$probe_arg"
  done <<EOF
$(docker inspect -f '{{range .Config.Healthcheck.Test}}{{println .}}{{end}}' "$probe_container" 2>/dev/null)
EOF
  case "${1:-}" in
    CMD) shift; docker exec "$probe_container" "$@" >/dev/null 2>&1 ;;
    CMD-SHELL) docker exec "$probe_container" sh -c "$2" >/dev/null 2>&1 ;;
    *) return 1 ;;
  esac
}

wait_until_serving() {
  echo "Waiting for $1 to become healthy..."
  attempt=0
  until probe_now "$compose_project-$1-1"; do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge 30 ]; then
      compose -p "$compose_project" --env-file "$acervo_root/deployment.env" --env-file "$acervo_root/secrets.env" --env-file "$acervo_root/llm.env" -f "$compose_file" logs "$1" >&2
      exit 1
    fi
    sleep 2
  done
}

wait_until_serving anki-sync-server

# Liveness, not readiness: the corpus service answers 503 on /health/ready until an index has been
# built, which is the correct state on a first deployment. Its healthcheck therefore asks whether it
# is serving, and Settings ▸ Clips is where "does it have a corpus yet" is answered.
wait_until_serving speech-retrieval

# Liveness, not readiness, and specifically not "has it got its samples": a fresh deployment has no
# sample bundle and serves perfectly well without one, offering the sample-free palette. Gating here
# would fail the install of a working service. The container says which state it is in on its first
# log line, and /api/v1/schema answers it for the interface.
wait_until_serving lexibeat

wait_until_serving server

# Asking the container whether it is healthy is not the same question as asking whether anyone can
# reach it: the healthcheck runs inside the container and knows nothing about publishing. This is the
# check that catches a container serving perfectly on a port bound to nothing, which is what the line
# below used to claim its way past. `docker port` rather than an HTTP request on purpose — it is the
# precise signal, and it needs no client this host might not have.
published=$(docker port "$compose_project-server-1" 8000 2>/dev/null || true)
if [ -z "$published" ]; then
  echo "The Acervo server is running but its port is not published, so nothing can reach it." >&2
  echo "Remove the container and deploy again: docker rm -f $compose_project-server-1" >&2
  exit 1
fi

printf '%s\n' "$release_dir" >"$acervo_root/current-release"

# Prune old release trees, keeping the current one and the two before it. Only reached once the
# deployment is healthy and `current-release` has been repointed, so a failed deploy prunes nothing
# and leaves every tree it might be diagnosed from.
#
# Each tree carries the compiled dictionaries and the macOS application, so an unpruned `releases/`
# grows by hundreds of megabytes per deployment — 48 of them had accumulated before this existed.
# Nothing rolls back to an old release (there is no such command), so the ones kept are for looking
# at, not for running. The current one must survive: `run-worker.sh` reads its compose file.
release_keep=3
if [ -d "$acervo_root/releases" ]; then
  # Sorted by name, which for these UTC timestamps is chronological. The current release is excluded
  # from the list rather than trusted to sort last, because `--local` deploys from a checkout whose
  # directory is not under `releases/` at all.
  stale_releases=$(mktemp)
  find "$acervo_root/releases" -mindepth 1 -maxdepth 1 -type d \
    ! -name "$(basename "$release_dir")" | sort >"$stale_releases"
  stale_total=$(wc -l <"$stale_releases" | tr -d " ")
  # `head -n` with a positive count, not GNU's negative form: this script also runs on macOS.
  stale_remove=$((stale_total - (release_keep - 1)))
  if [ "$stale_remove" -gt 0 ]; then
    head -n "$stale_remove" "$stale_releases" | while IFS= read -r stale; do
      case "$stale" in
        "$acervo_root/releases/"*) rm -rf -- "$stale" ;;
      esac
    done
    echo "Pruned $stale_remove old release tree(s), keeping $release_keep"
  fi
  rm -f "$stale_releases"
fi
echo "Acervo Anki sync server is healthy at $bind_address:$anki_port"
echo "Acervo internal HTTP backend is healthy at http://$app_bind_address:$app_port"
# Said again here because the line above it scrolled past in the build output: this is the copy to
# delete, by hand, once the converted database has proved itself.
if [ "$transition" = true ]; then
  echo "The database was converted. Its backup, from before the conversion, is at $backup_dir/server"
fi
echo "Open the separately configured HTTPS reverse-proxy or Tailscale Serve address; this deployment does not claim the host's default HTTPS endpoint."

#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
profile=${ACERVO_DEPLOY_PROFILE:-"$repo_root/.acervo-deploy"}
# What this machine remembers having sent, so a deploy can leave it out. Beside the build products
# and as disposable: without it the next deploy sends everything, which is only slower.
deploy_state=${ACERVO_DEPLOY_STATE:-"$repo_root/build/deploy-state"}
helper_path=/usr/local/sbin/deploy-acervo
helper_protocol=14
worker_arguments=

mode=
target=
acervo_root=
configure=false
configure_llm=false
llm_chain=
llm_settings=
llm_key_name=
llm_api_key_stdin=false
google_credentials=
reset_anki=false
timezone=
reset_database=false
transition=false
rebuild=false
cancel_jobs=false
jobs_arguments=
remember=false
bind_address=
anki_port=
app_bind_address=
app_port=
https_port=
service=
action=deploy

usage() {
  cat >&2 <<'EOF'
usage:
  ./deploy.sh --local [--root PATH] [--bind-address ADDRESS] [--port PORT]
              [--app-bind-address ADDRESS] [--app-port PORT]
              [--configure-credentials] [--reset-anki] [--reset-database | --transition]
              [--cancel-jobs] [--rebuild] [--timezone ZONE]
              [--configure-llm [--llm-chain IDS] [--llm-set NAME=VALUE]...
               [--llm-key NAME --llm-api-key-stdin]]
  ./deploy.sh [--target USER@HOST] [--root PATH] [--configure-credentials]
              [--bind-address ADDRESS] [--port PORT] [--remember-target]
              [--app-bind-address ADDRESS] [--app-port PORT]
              [--https-port PORT] [--service NAME] [--reset-anki]
              [--reset-database | --transition] [--cancel-jobs] [--rebuild]
              [--timezone ZONE]
       deploy.sh --jobs open | cancel
              [--configure-llm [--llm-chain IDS] [--llm-set NAME=VALUE]...
               [--llm-key NAME --llm-api-key-stdin]]
  ./deploy.sh [--target USER@HOST] [--remember-target] --install-helper
  ./deploy.sh [--target USER@HOST] [--https-port PORT | --service NAME] --configure-https
  ./deploy.sh [--local | --target USER@HOST] --create-account
  ./deploy.sh [--local | --target USER@HOST] --status
  ./deploy.sh [--target USER@HOST] --worker OPERATION [ARGUMENT...]

  --service NAME      publish through the Tailscale service svc:NAME on its own
                      hostname and its own 443, instead of a host port. Needed
                      for Android to install this app alongside another PWA on
                      the same machine; takes precedence over --https-port
  --reset-anki        replace the Anki sync server's collection and the robot's with empty
                      ones. The vocabulary, its pictures and recordings are untouched
  --timezone ZONE     the zone the server reads days and the nightly hour in, such as
                      Europe/London. Without it, this machine's own zone is used, and
                      failing that the one the server already has
  --reset-database    replace the vocabulary database from scratch; accounts go with
                      it and are recreated with --create-account. Anki data is untouched
  --transition        carry the vocabulary database across a schema change instead of
                      rebuilding it. Takes no argument: it reads the revision the database
                      is stamped with and runs the converter this release ships for that
                      revision, after a dry run and a backup. A database already current is
                      left alone; one no converter fits is refused and nothing is deployed.
                      The backup goes in the dated directory under the deployment's
                      backups/, and its path is printed
  --rebuild           rebuild everything instead of only what changed: every image from
                      its first layer, with the base image pulled again, and every compiled
                      dictionary sent again. A deploy otherwise reuses each image layer
                      whose inputs are unchanged and sends only the dictionaries that
                      changed since this machine's last deploy there. Around a quarter of
                      an hour; for when a reused layer is suspected, or the server has lost
                      its dictionaries
  --cancel-jobs       cancel the server's open jobs instead of refusing to deploy. It may be
                      given with --transition, which is the combination to reach for when a
                      schema change is waiting behind an open job: nothing is deployed until
                      the jobs have gone, and the converter then runs against a stopped server
  --jobs OPERATION    ask the server about its jobs and deploy nothing: `open` or `cancel`,
                      which are what the launcher's fixed operation list offers. The way out
                      when a deploy cannot run yet — a database waiting for --transition
                      cannot start, so a deploy that would have cancelled the jobs for you
                      never gets that far
                      while they run. A deploy never carries a job across versions
  --create-account    create one account on the running server, reading the address
                      and password from the terminal
  --install-samples   fetch the loop generator's sample pack — about 3.1 GB, once —
                      into the directory the running service mounts. Without it no
                      loop can be made. The URL and digest come from the pin, so
                      neither is typed by hand
  --configure-llm     update only the server's durable llm.env; existing server,
                      Anki and other providers' credentials are retained
  --llm-chain IDS     which providers answer, in order, as comma-separated ids
                      from models/catalogue.json. Empty means every provider
                      this server has credentials for, in catalogue order
  --llm-set NAME=VAL  set one non-secret provider variable, e.g. an account id
                      or a Vertex project. Repeatable
  --llm-key NAME      which key variable the value on standard input is
  --google-credentials FILE
                      Google credentials for Vertex, which will not
                      authenticate from a variable. Either a service-account
                      key or the file `gcloud auth application-default login`
                      writes. Installed mode 600 and mounted read-only
EOF
  exit 2
}

choose_action() {
  [ "$action" = deploy ] || usage
  action=$1
}

# A step says what stage it is in and what it produced; a bundler's asset table says neither, so it
# is kept until it is worth reading. On failure everything the step wrote is printed before the
# script stops. Deliberately not a pipeline: this is POSIX sh, where pipefail does not exist and a
# pipe would discard the step's own exit status.
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

while [ "$#" -gt 0 ]; do
  case "$1" in
    --local) mode=local; shift ;;
    --target) [ "$#" -ge 2 ] || usage; target=$2; shift 2 ;;
    --root) [ "$#" -ge 2 ] || usage; acervo_root=$2; shift 2 ;;
    --configure-credentials) configure=true; shift ;;
    --configure-llm) configure_llm=true; shift ;;
    --llm-chain) [ "$#" -ge 2 ] || usage; llm_chain=$2; shift 2 ;;
    --llm-set) [ "$#" -ge 2 ] || usage; llm_settings="$llm_settings$2
"; shift 2 ;;
    --llm-key) [ "$#" -ge 2 ] || usage; llm_key_name=$2; shift 2 ;;
    --google-credentials) [ "$#" -ge 2 ] || usage; google_credentials=$2; shift 2 ;;
    --llm-api-key-stdin) llm_api_key_stdin=true; shift ;;
    --remember-target) remember=true; shift ;;
    --bind-address) [ "$#" -ge 2 ] || usage; bind_address=$2; shift 2 ;;
    --port) [ "$#" -ge 2 ] || usage; anki_port=$2; shift 2 ;;
    --app-bind-address) [ "$#" -ge 2 ] || usage; app_bind_address=$2; shift 2 ;;
    --app-port) [ "$#" -ge 2 ] || usage; app_port=$2; shift 2 ;;
    --https-port) [ "$#" -ge 2 ] || usage; https_port=$2; shift 2 ;;
    --service) [ "$#" -ge 2 ] || usage; service=$2; shift 2 ;;
    --install-helper) choose_action install-helper; shift ;;
    --configure-https) choose_action configure-https; shift ;;
    --status) choose_action status; shift ;;
    # Everything after --worker belongs to the worker, so parsing stops here rather than trying to
    # tell an operation's flags apart from this script's.
    --worker) choose_action worker; shift; worker_arguments=$*; break ;;
    --jobs) choose_action jobs; shift; jobs_arguments=$*; break ;;
    --create-account) choose_action create-account; shift ;;
    --install-samples) choose_action install-samples; shift ;;
    --reset-anki) reset_anki=true; shift ;;
    --timezone) [ "$#" -ge 2 ] || usage; timezone=$2; shift 2 ;;
    --reset-database) reset_database=true; shift ;;
    --transition) transition=true; shift ;;
    --rebuild) rebuild=true; shift ;;
    --cancel-jobs) cancel_jobs=true; shift ;;
    *) usage ;;
  esac
done

read_profile() {
  [ -f "$profile" ] || return 0
  first_line=$(sed -n '/[^[:space:]]/ { p; q; }' "$profile")
  case "$first_line" in
    *=*)
      while IFS='=' read -r key value; do
        case "$key" in
          ''|'#'*) continue ;;
          DEPLOY_TARGET) profile_target=$value ;;
          ACERVO_ROOT) profile_root=$value ;;
          ACERVO_BIND_ADDRESS) profile_bind_address=$value ;;
          ACERVO_ANKI_PORT) profile_anki_port=$value ;;
          ACERVO_APP_BIND_ADDRESS) profile_app_bind_address=$value ;;
          ACERVO_APP_PORT) profile_app_port=$value ;;
          ACERVO_HTTPS_PORT) profile_https_port=$value ;;
          ACERVO_SERVICE) profile_service=$value ;;
          *) echo "Unknown setting in .acervo-deploy: $key" >&2; exit 2 ;;
        esac
      done <"$profile"
      ;;
    *) profile_target=$first_line ;;
  esac
}

validate_address() {
  label=$1
  value=$2
  case "$value" in
    ''|*[!A-Za-z0-9:._-]*) echo "Unsafe $label" >&2; exit 2 ;;
  esac
}

validate_port() {
  label=$1
  value=$2
  case "$value" in
    ''|*[!0-9]*) echo "$label must be numeric" >&2; exit 2 ;;
  esac
  if [ "$value" -lt 1 ] || [ "$value" -gt 65535 ]; then
    echo "$label must be between 1 and 65535" >&2
    exit 2
  fi
}

write_profile() {
  umask 077
  {
    printf 'DEPLOY_TARGET=%s\n' "$target"
    printf 'ACERVO_ROOT=%s\n' "$acervo_root"
    printf 'ACERVO_BIND_ADDRESS=%s\n' "$effective_bind_address"
    printf 'ACERVO_ANKI_PORT=%s\n' "$effective_anki_port"
    printf 'ACERVO_APP_BIND_ADDRESS=%s\n' "$effective_app_bind_address"
    printf 'ACERVO_APP_PORT=%s\n' "$effective_app_port"
    printf 'ACERVO_HTTPS_PORT=%s\n' "$effective_https_port"
    printf 'ACERVO_SERVICE=%s\n' "$service"
  } >"$profile"
  chmod 600 "$profile"
}

profile_target=
profile_root=
profile_bind_address=
profile_anki_port=
profile_app_bind_address=
profile_app_port=
profile_https_port=
profile_service=
if [ "$mode" != local ]; then
  read_profile
  target=${target:-$profile_target}
  acervo_root=${acervo_root:-$profile_root}
  bind_address=${bind_address:-$profile_bind_address}
  anki_port=${anki_port:-$profile_anki_port}
  app_bind_address=${app_bind_address:-$profile_app_bind_address}
  app_port=${app_port:-$profile_app_port}
  https_port=${https_port:-$profile_https_port}
  service=${service:-$profile_service}
fi

effective_bind_address=${bind_address:-127.0.0.1}
effective_anki_port=${anki_port:-27701}
effective_app_bind_address=${app_bind_address:-127.0.0.1}
effective_app_port=${app_port:-27702}
effective_https_port=${https_port:-27702}
validate_address "bind address" "$effective_bind_address"
validate_address "app bind address" "$effective_app_bind_address"
validate_port "Anki port" "$effective_anki_port"
validate_port "App port" "$effective_app_port"
validate_port "HTTPS port" "$effective_https_port"
# A Tailscale service listens on its own virtual IP, so its 443 is not the host's 443 and cannot
# collide with another application. Android only mints a WebAPK for a default port, so a service is
# what lets Acervo install alongside another self-hosted PWA rather than replacing it.
if [ -n "$service" ]; then
  # Spelled out rather than `a-z`: a bracket range follows the locale's collation, and under
  # en_GB.UTF-8 `[a-z]` matches capitals too.
  case "$service" in
    ''|*[!abcdefghijklmnopqrstuvwxyz0123456789-]*)
      echo "The service name must use lowercase letters, digits and hyphens" >&2
      exit 2
      ;;
  esac
fi
[ "$effective_anki_port" != "$effective_app_port" ] || {
  echo "The Acervo app port must differ from the Anki sync port" >&2
  exit 2
}

if [ "$mode" = local ] && { [ "$action" = install-helper ] || [ "$action" = configure-https ]; }; then
  usage
fi
if [ "$configure" = true ] && [ "$action" != deploy ]; then usage; fi
if [ "$configure_llm" = true ] && [ "$action" != deploy ]; then usage; fi
if [ "$reset_anki" = true ] && [ "$action" != deploy ]; then usage; fi
if [ -n "$timezone" ] && [ "$action" != deploy ]; then usage; fi
if [ "$reset_database" = true ] && [ "$action" != deploy ]; then usage; fi
if [ "$transition" = true ] && [ "$action" != deploy ]; then usage; fi
if [ "$rebuild" = true ] && [ "$action" != deploy ]; then usage; fi
# Opposite answers to the same schema change: rebuild it, or carry it across.
if [ "$transition" = true ] && [ "$reset_database" = true ]; then usage; fi

# The zone the server reads days and the nightly hour in, which is the owner's and so this machine's:
# `--timezone`, else `TZ`, else what /etc/localtime links to. Written into deployment.env on every
# deploy, because the installer rewrites that file whole; empty leaves the server's zone as it was.
local_timezone() {
  zone=${TZ:-}
  zone=${zone#:}
  if [ -z "$zone" ] && link=$(readlink /etc/localtime 2>/dev/null); then
    case "$link" in *zoneinfo/*) zone=${link#*zoneinfo/} ;; esac
  fi
  if [ -z "$zone" ] && [ -r /etc/timezone ]; then
    IFS= read -r zone </etc/timezone || true
  fi
  printf '%s' "$zone"
}
is_timezone() {
  case "$1" in ''|/*|*/|*[!A-Za-z0-9/_+-]*) return 1 ;; esac
}
effective_timezone=$timezone
if [ -n "$effective_timezone" ]; then
  is_timezone "$effective_timezone" || { echo "Not a timezone name: $effective_timezone" >&2; exit 2; }
elif [ "$action" = deploy ]; then
  effective_timezone=$(local_timezone)
  # A POSIX rule in TZ (`<+03>-3`) is not a zone name the server can look up; leave the server's.
  is_timezone "$effective_timezone" || effective_timezone=
fi

if [ "$configure_llm" = false ]; then
  [ -z "$llm_chain$llm_settings$llm_key_name$google_credentials" ] \
    && [ "$llm_api_key_stdin" = false ] || usage
else
  [ "$configure" = false ] || {
    echo "Configure server credentials and the LLM in separate commands" >&2
    exit 2
  }
  [ -n "$llm_chain$llm_settings$llm_key_name$google_credentials" ] || {
    echo "--configure-llm needs one of --llm-chain, --llm-set, --llm-key or --google-credentials" >&2
    exit 2
  }
  if [ -n "$google_credentials" ]; then
    [ -f "$google_credentials" ] || { echo "No such file: $google_credentials" >&2; exit 2; }
    # Refused here rather than discovered at the first capture, a deployment later.
    grep -qE '"type"[[:space:]]*:[[:space:]]*"(service_account|authorized_user)"' "$google_credentials" || {
      echo "$google_credentials is neither a service-account key nor an" >&2
      echo "application-default credentials file" >&2
      exit 2
    }
    # The path names where the container will read it, not where it is now.
    llm_settings="${llm_settings}GOOGLE_APPLICATION_CREDENTIALS=/run/acervo/credentials/google.json
"
  fi
  # A provider is a row in models/catalogue.json, so there is no list of provider names here and no
  # known-wrong model ids to keep up to date. What a name has to be is a variable the catalogue
  # actually reads; the installer checks that against the catalogue it was shipped, which is the one
  # the server will run.
  printf '%s' "$llm_settings" | while IFS= read -r setting; do
    [ -n "$setting" ] || continue
    case "$setting" in
      *=*) ;;
      *) echo "--llm-set takes NAME=VALUE, not $setting" >&2; exit 2 ;;
    esac
    case "${setting%%=*}" in
      ''|*[!A-Z0-9_]*) echo "Unsafe LLM variable name: ${setting%%=*}" >&2; exit 2 ;;
    esac
    # Commas for a chain, colons and slashes for a base URL. Nothing here is ever evaluated — it is
    # printf'd into a file — but a value that cannot be written on one line is a mistake either way.
    case "${setting#*=}" in
      *[!A-Za-z0-9._:/,-]*) echo "Unsafe LLM configuration value" >&2; exit 2 ;;
    esac
  done || exit 2
  case "$llm_chain" in
    *[!A-Za-z0-9._,-]*) echo "--llm-chain takes comma-separated provider ids" >&2; exit 2 ;;
  esac
  case "$llm_key_name" in
    ''|*[!A-Z0-9_]*) [ -z "$llm_key_name" ] || { echo "Unsafe LLM key name: $llm_key_name" >&2; exit 2; } ;;
  esac
  [ -n "$llm_key_name" ] || [ "$llm_api_key_stdin" = false ] || {
    echo "--llm-api-key-stdin needs --llm-key NAME to say which variable it is" >&2
    exit 2
  }
  llm_api_key=
  if [ -n "$llm_key_name" ]; then
    if [ "$llm_api_key_stdin" = true ]; then
      IFS= read -r llm_api_key || true
    else
      printf '%s' "$llm_key_name: " >&2
      if [ -t 0 ]; then
        stty -echo
        trap 'stty echo' EXIT HUP INT TERM
        IFS= read -r llm_api_key
        stty echo
        trap - EXIT HUP INT TERM
        printf '\n' >&2
      else
        echo "--llm-api-key-stdin is required when standard input is not a terminal" >&2
        exit 2
      fi
    fi
    case "$llm_api_key" in
      ''|*[!A-Za-z0-9._-]*) echo "A valid LLM API key is required" >&2; exit 2 ;;
    esac
  fi
fi

if [ "$reset_anki" = true ]; then
  echo "This empties Anki: the sync server's collection and the robot's. Your words, pictures and"
  echo "recordings are not touched. Keep Anki closed on every device until the bootstrap has run."
  printf '%s' 'Type RESET ACERVO ANKI to continue: '
  IFS= read -r reset_confirmation
  [ "$reset_confirmation" = 'RESET ACERVO ANKI' ] || {
    echo "Reset cancelled" >&2
    exit 2
  }
fi

if [ "$reset_database" = true ]; then
  echo 'This replaces the vocabulary database. Every account, word and revision on the server is'
  echo 'discarded; accounts must be recreated afterwards. Device replicas are not touched, and a'
  echo 'copy of the old database is kept under the deployment backups directory.'
  printf '%s' 'Type RESET ACERVO VOCABULARY to continue: '
  IFS= read -r reset_database_confirmation
  [ "$reset_database_confirmation" = 'RESET ACERVO VOCABULARY' ] || {
    echo "Reset cancelled" >&2
    exit 2
  }
fi

prompt_credentials() {
  printf '%s' 'Initial Anki sync username: ' >&2
  IFS= read -r sync_username
  printf '%s' 'Initial Anki sync password: ' >&2
  if [ -t 0 ]; then
    stty -echo
    trap 'stty echo' EXIT HUP INT TERM
    IFS= read -r sync_password
    stty echo
    trap - EXIT HUP INT TERM
  else
    IFS= read -r sync_password
  fi
  printf '\n' >&2
  [ -n "$sync_username" ] && [ -n "$sync_password" ] || {
    echo "Username and password are required" >&2
    exit 2
  }
  case "$sync_username$sync_password" in
    *:*) echo "Anki sync credentials may not contain a colon" >&2; exit 2 ;;
  esac
}

# One account on the running server. `admin.py accounts create` is the only thing that makes one —
# there is no superuser to have — and it reads the password from stdin, so this streams it straight
# into the container rather than putting it on a command line.
prompt_account() {
  printf '%s' 'Account email address: ' >&2
  IFS= read -r account_email
  printf '%s' 'Password (at least 8 characters): ' >&2
  if [ -t 0 ]; then
    stty -echo
    trap 'stty echo' EXIT HUP INT TERM
    IFS= read -r account_password
    stty echo
    trap - EXIT HUP INT TERM
  else
    IFS= read -r account_password
  fi
  printf '\n' >&2
  [ -n "$account_email" ] && [ -n "$account_password" ] || {
    echo "An email address and a password are required" >&2
    exit 2
  }
  # Checked here because the address is the one part of this that reaches a remote shell as text.
  # The password never does: it goes over stdin and is never an argument.
  case "$account_email" in
    *[!A-Za-z0-9@._+-]*) echo "An email address may only contain letters, digits and @._+-" >&2; exit 2 ;;
    *@*) ;;
    *) echo "That does not look like an email address" >&2; exit 2 ;;
  esac
}

# The compiled dictionaries are most of a release — 800-odd MB against a few MB of everything else —
# and they change when one is recompiled, not when the code does. The installer merges whatever a
# release carries into what the server already publishes, so a release may carry only the changed
# ones: this is the record of what the last successful deploy to this destination left there, as
# checksums, which the packager compares against. Written only after the installer has succeeded,
# so a failed deploy is sent again in full. `--rebuild` ignores it.
dictionaries_sent_file() {
  printf '%s/dictionaries-%s\n' "$deploy_state" \
    "$(printf '%s' "${target:-local}:$acervo_root" | cksum | cut -d ' ' -f 1)"
}

remember_sent_dictionaries() {
  [ -f "$1.dictionaries" ] || return 0
  mkdir -p "$deploy_state"
  mv "$1.dictionaries" "$(dictionaries_sent_file)"
}

build_release_archive() {
  if [ "$rebuild" = false ]; then
    ACERVO_DICTIONARIES_SENT=$(dictionaries_sent_file)
    export ACERVO_DICTIONARIES_SENT
  fi
  eval "$("$repo_root/scripts/version.sh")"
  export ACERVO_APP_VERSION ACERVO_APP_BUILD
  if [ "$(uname -s)" = Darwin ] && [ "${ACERVO_SKIP_MACOS_RELEASE:-false}" != true ]; then
    "$repo_root/scripts/package_macos_release.sh" >&2
    ACERVO_INCLUDE_MACOS_RELEASE=true
  else
    ACERVO_INCLUDE_MACOS_RELEASE=false
  fi
  export ACERVO_INCLUDE_MACOS_RELEASE
  if [ "${ACERVO_SKIP_APP_BUILD:-false}" != true ]; then
    echo "Building the web app..." >&2
    run_quietly "The web build" npm run stage:pwa
  fi
  "$repo_root/scripts/package_acervo_server.sh"
}

# `admin.py accounts create` reads the password from stdin, so nothing sensitive reaches a command
# line or a process list. Used directly where the invoking account can reach docker; where the
# passwordless launcher is what has that access, it runs the same command on the far side.
create_account_command='docker exec -i acervo-server-1 python -m acervo.admin accounts create --email'

# A deploy never pauses or serialises a job: it refuses while any are open, or cancels them when told
# to (`docs/architecture/jobs.md`). The count comes from the running server as one line of
# JSON; no answer at all — no container yet, or a server from before jobs existed — means nothing is
# open. `--reset-database` skips the question, because the table goes with the database.
refuse_open_jobs() {
  open_report=$1
  open_count=$(printf '%s\n' "$open_report" | sed -n 's/.*"open": *\([0-9][0-9]*\).*/\1/p' | head -n 1)
  [ -n "$open_count" ] && [ "$open_count" -gt 0 ] || return 0
  open_kinds=$(printf '%s\n' "$open_report" \
    | sed -n 's/.*"byKind": *{\([^}]*\)}.*/\1/p' \
    | sed 's/"\([^"]*\)": *\([0-9][0-9]*\)/\2 \1/g')
  echo "Refusing to deploy: $open_count jobs are open ($open_kinds)." >&2
  echo "Wait for them, or run ./deploy.sh --cancel-jobs." >&2
  exit 1
}

jobs_command='docker exec acervo-server-1 python -m acervo.admin jobs'

# The sample pack's URL and digest, from the pin rather than from the owner's memory. Read on this
# side, where the repository is; the far side only checks that they are the shape they should be.
read_pin_url() {
  pin=$(dirname "$0")/deploy/acervo/lexibeat/pin.json
  [ -f "$pin" ] || { echo "Missing pin: $pin" >&2; exit 1; }
  # Concatenation rather than an f-string: same-quoted nesting inside one is a syntax error before
  # Python 3.12, and this runs on whatever `python3` the invoking machine happens to have.
  # One `--from` per part, in order: GitHub refuses a release asset of 2 GiB or more, so the bundle
  # is published in parts and the fetch joins them before checking the whole archive's digest.
  bundle_from=$(python3 -c '
import json, sys
pin = json.load(open(sys.argv[1], encoding="utf-8"))
base = pin["repository"] + "/releases/download/" + pin["bundle"]["release"] + "/"
print(" ".join("--from " + base + part for part in pin["bundle"]["parts"]))
' "$pin")
  bundle_sha=$(python3 -c '
import json, sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["bundle"]["sha256"])
' "$pin")
}

if [ "$mode" = local ]; then
  if [ "$action" = create-account ]; then
    prompt_account
    printf '%s\n' "$account_password" | $create_account_command "$account_email"
    exit $?
  fi
  if [ "$action" = jobs ]; then
  # The jobs command on its own, deploying nothing. `--cancel-jobs` cancels *and then deploys*,
  # which is the wrong shape when the deploy is what cannot run: a database waiting for a converter
  # refuses to start, so the server never comes back up to be asked again.
  if [ "$remote_mode" = root ]; then
    echo "--jobs needs the reviewed launcher; install it once with ./deploy.sh --install-helper" >&2
    exit 2
  fi
  [ -n "$jobs_arguments" ] || usage
  ssh -T "$target" "sudo -n $helper_path jobs $jobs_arguments"
  exit $?
fi


if [ "$action" = install-samples ]; then
    # Locally there is no launcher and no ssh: the same compose invocation, run here. The env file
    # is the point of it either way — without it compose falls back to a named volume and the
    # bundle lands somewhere the service does not mount.
    read_pin_url
    docker compose -p "${ACERVO_COMPOSE_PROJECT:-acervo}" \
      --env-file "$acervo_root/deployment.env" \
      --env-file "$acervo_root/secrets.env" \
      --env-file "$acervo_root/llm.env" \
      -f "$(dirname "$0")/deploy/acervo/compose.yaml" \
      run --rm lexibeat lexibeat-bundle fetch --into /var/lib/lexibeat/bundle \
      $bundle_from --sha256 "$bundle_sha"
    exit $?
  fi
  if [ "$action" = status ]; then
    docker inspect --format='state={{.State.Status}}, health={{.State.Health.Status}}' acervo-anki-sync-server-1
    docker port acervo-anki-sync-server-1 8080
    docker inspect --format='state={{.State.Status}}, health={{.State.Health.Status}}' acervo-server-1
    docker port acervo-server-1 8000
    exit 0
  fi
  [ -n "$acervo_root" ] || acervo_root=${ACERVO_LOCAL_ROOT:-"$HOME/.acervo"}
  if [ "$reset_database" = false ]; then
    if [ "$cancel_jobs" = true ]; then
      $jobs_command cancel --all 2>/dev/null || true
    else
      refuse_open_jobs "$($jobs_command open --json 2>/dev/null || true)"
    fi
  fi
  local_archive=$(build_release_archive)
  credential_args=
  if [ "$configure_llm" = true ] && [ ! -f "$acervo_root/secrets.env" ]; then
    echo "Configure the server credentials first with --configure-credentials" >&2
    exit 2
  fi
  if [ "$configure" = true ] || [ ! -f "$acervo_root/secrets.env" ]; then
    prompt_credentials
    credential_args=--credentials-stdin
  fi
  llm_credentials=
  if [ "$configure_llm" = true ]; then
    llm_credentials=$(mktemp "${TMPDIR:-/tmp}/acervo-llm.XXXXXX")
    trap '[ -z "${llm_credentials:-}" ] || rm -f "$llm_credentials"' EXIT HUP INT TERM
    chmod 600 "$llm_credentials"
    {
      [ -z "$llm_chain" ] || printf 'ACERVO_TEXT_CHAIN=%s\n' "$llm_chain"
      printf '%s' "$llm_settings"
      [ -z "$llm_key_name" ] || printf '%s=%s\n' "$llm_key_name" "$llm_api_key"
    } >"$llm_credentials"
  fi
  set -- --root "$acervo_root" --archive "$local_archive" \
    --bind-address "$effective_bind_address" --port "$effective_anki_port" \
    --app-bind-address "$effective_app_bind_address" --app-port "$effective_app_port"
  [ -z "$credential_args" ] || set -- "$@" "$credential_args"
  [ -z "$llm_credentials" ] || set -- "$@" --llm-credentials-file "$llm_credentials"
  [ -z "$google_credentials" ] || set -- "$@" --google-credentials-file "$google_credentials"
  [ "$reset_anki" = false ] || set -- "$@" --reset-anki
  [ -z "$effective_timezone" ] || set -- "$@" --timezone "$effective_timezone"
  [ "$reset_database" = false ] || set -- "$@" --reset-database
  [ "$transition" = false ] || set -- "$@" --transition
  [ "$rebuild" = false ] || set -- "$@" --rebuild
  if [ -n "$credential_args" ]; then
    printf '%s\n%s\n' "$sync_username" "$sync_password" | "$repo_root/deploy/acervo/install.sh" "$@"
  else
    "$repo_root/deploy/acervo/install.sh" "$@"
  fi
  remember_sent_dictionaries "$local_archive"
  [ -z "$llm_credentials" ] || rm -f "$llm_credentials"
  llm_credentials=
  trap - EXIT HUP INT TERM
  exit 0
fi

[ -n "$target" ] || usage
case "$target" in *[!A-Za-z0-9_.@:-]*) echo "Unsafe SSH target" >&2; exit 2 ;; esac
if [ -n "$acervo_root" ]; then
  case "$acervo_root" in /*/acervo) ;; *) echo "Remote root must be an absolute path ending in /acervo" >&2; exit 2 ;; esac
  case "$acervo_root" in *[!A-Za-z0-9_./-]*) echo "Unsafe remote root" >&2; exit 2 ;; esac
fi
if [ "$remember" = true ]; then write_profile; fi

if [ "$action" = install-helper ]; then
  remote_helper="/tmp/deploy-acervo-$$"
  echo "Uploading the reviewed Acervo deployment launcher..."
  ssh -T "$target" "umask 077 && cat > $remote_helper" <"$repo_root/deploy/acervo/remote-helper.sh"
  echo "Installing the launcher (sudo asks once; routine deployments will not)..."
  ssh -t "$target" \
    "sudo sh $remote_helper --install; result=\$?; rm -f $remote_helper; exit \$result"
  exit 0
fi

remote_probe=$(ssh -T "$target" \
  "if [ \"\$(id -u)\" -eq 0 ]; then echo root; \
   elif report=\$(sudo -n $helper_path check 2>/dev/null) && \
        [ \"\$report\" = 'acervo-deploy-protocol: $helper_protocol' ]; then echo helper; \
   else echo missing; fi")
remote_mode=$(printf '%s\n' "$remote_probe" | tail -n 1)
case "$remote_mode" in
  root|helper) ;;
  *)
    echo "The passwordless Acervo launcher is missing or incompatible on $target." >&2
    echo "Install or refresh it once with: ./deploy.sh --install-helper" >&2
    exit 1
    ;;
esac

if [ "$action" = status ]; then
  if [ "$remote_mode" = root ]; then
    ssh -T "$target" 'docker_path=$(command -v docker || true); \
      [ -n "$docker_path" ] || docker_path=/var/packages/ContainerManager/target/usr/bin/docker; \
      "$docker_path" inspect --format=state={{.State.Status}},health={{.State.Health.Status}} acervo-anki-sync-server-1 && \
      "$docker_path" port acervo-anki-sync-server-1 8080 && \
      "$docker_path" inspect --format=state={{.State.Status}},health={{.State.Health.Status}} acervo-server-1 && \
      "$docker_path" port acervo-server-1 8000'
  else
    ssh -T "$target" "sudo -n $helper_path status"
  fi
  exit 0
fi

if [ "$action" = worker ]; then
  # Straight through to the launcher, which finds the current release and runs its worker script as
  # root. Remote only: locally there is no launcher, and `run-worker.sh` is the direct call.
  if [ "$remote_mode" = root ]; then
    echo "--worker needs the reviewed launcher; install it once with ./deploy.sh --install-helper" >&2
    exit 2
  fi
  [ -n "$worker_arguments" ] || usage
  ssh -T "$target" "sudo -n $helper_path worker $worker_arguments"
  exit $?
fi


if [ "$action" = jobs ]; then
  # The jobs command on its own, deploying nothing. `--cancel-jobs` cancels *and then deploys*,
  # which is the wrong shape when the deploy is what cannot run: a database waiting for a converter
  # refuses to start, so the server never comes back up to be asked again.
  if [ "$remote_mode" = root ]; then
    echo "--jobs needs the reviewed launcher; install it once with ./deploy.sh --install-helper" >&2
    exit 2
  fi
  [ -n "$jobs_arguments" ] || usage
  ssh -T "$target" "sudo -n $helper_path jobs $jobs_arguments"
  exit $?
fi


if [ "$action" = install-samples ]; then
  # The URL and the digest come from the pin on this side, where the repository is — so the owner
  # never copies a 64-character digest, and the far side only checks their shape.
  read_pin_url
  if [ "$remote_mode" = root ]; then
    echo "--install-samples needs the reviewed launcher; install it once with ./deploy.sh --install-helper" >&2
    exit 2
  fi
  ssh -T "$target" "sudo -n $helper_path install-samples $bundle_from --sha256 '$bundle_sha'"
  exit $?
fi

if [ "$action" = create-account ]; then
  prompt_account
  if [ "$remote_mode" = root ]; then
    printf '%s\n' "$account_password" | ssh -T "$target" \
      "$create_account_command '$account_email'"
  else
    # Two lines, positional, the way every other credential stream in this deployment works.
    printf '%s\n%s\n' "$account_email" "$account_password" | \
      ssh -T "$target" "sudo -n $helper_path create-account"
  fi
  exit $?
fi

if [ "$action" = configure-https ]; then
  # The service and the host-port listener are alternatives, not layers. A configured service owns
  # the public address, and the remembered HTTPS port is left unused rather than mapped as well.
  if [ -n "$service" ]; then
    https_arguments="--service $service"
    echo "Configuring the Tailscale service svc:$service (HTTPS 443)."
  else
    https_arguments="--https-port $effective_https_port"
  fi
  if [ "$remote_mode" = root ]; then
    ssh -T "$target" "sh -s -- configure-https $https_arguments --app-port $effective_app_port" \
      <"$repo_root/deploy/acervo/remote-helper.sh"
  else
    ssh -T "$target" \
      "sudo -n $helper_path configure-https $https_arguments --app-port $effective_app_port"
  fi
  exit 0
fi

if [ "$reset_database" = false ]; then
  if [ "$remote_mode" = helper ]; then
    remote_jobs="sudo -n $helper_path jobs"
  else
    remote_jobs='docker_path=$(command -v docker || true); \
      [ -n "$docker_path" ] || docker_path=/var/packages/ContainerManager/target/usr/bin/docker; \
      "$docker_path" exec acervo-server-1 python -m acervo.admin jobs'
  fi
  if [ "$cancel_jobs" = true ]; then
    echo "Cancelling the server's open jobs..."
    if [ "$remote_mode" = helper ]; then
      ssh -T "$target" "$remote_jobs cancel" || true
    else
      ssh -T "$target" "$remote_jobs cancel --all" || true
    fi
  elif [ "$remote_mode" = helper ]; then
    refuse_open_jobs "$(ssh -T "$target" "$remote_jobs open" 2>/dev/null || true)"
  else
    refuse_open_jobs "$(ssh -T "$target" "$remote_jobs open --json" 2>/dev/null || true)"
  fi
fi

archive=$(build_release_archive)
remote_installer="/tmp/acervo-install-$$.sh"
remote_archive="/tmp/acervo-release-$$.tar.gz"
remote_credentials="/tmp/acervo-credentials-$$"
remote_llm_credentials="/tmp/acervo-llm-credentials-$$"
remote_google_credentials="/tmp/acervo-google-credentials-$$"
remote_cleanup() {
  ssh -T "$target" "rm -f $remote_installer $remote_archive $remote_credentials $remote_llm_credentials $remote_google_credentials" >/dev/null 2>&1 || true
}
remote_failed() {
  remote_cleanup
  echo "Acervo deployment failed on the remote server" >&2
  exit 1
}

credential_args=
if [ "$configure" = true ]; then
  prompt_credentials
  printf '%s\n%s\n' "$sync_username" "$sync_password" | \
    ssh -T "$target" "umask 077 && cat > $remote_credentials" || remote_failed
  credential_args="--credentials-file $remote_credentials"
fi

llm_credential_args=
if [ "$configure_llm" = true ]; then
  {
    [ -z "$llm_chain" ] || printf 'ACERVO_TEXT_CHAIN=%s\n' "$llm_chain"
    printf '%s' "$llm_settings"
    [ -z "$llm_key_name" ] || printf '%s=%s\n' "$llm_key_name" "$llm_api_key"
  } | ssh -T "$target" "umask 077 && cat > $remote_llm_credentials" || remote_failed
  llm_credential_args="--llm-credentials-file $remote_llm_credentials"
fi
if [ -n "$google_credentials" ]; then
  # Over stdin like every other secret: a path on a command line is visible in `ps`.
  ssh -T "$target" "umask 077 && cat > $remote_google_credentials" <"$google_credentials" || remote_failed
  llm_credential_args="$llm_credential_args --google-credentials-file $remote_google_credentials"
fi

installer_arguments=
[ -z "$acervo_root" ] || installer_arguments="$installer_arguments --root $acervo_root"
[ -z "$credential_args" ] || installer_arguments="$installer_arguments $credential_args"
[ -z "$llm_credential_args" ] || installer_arguments="$installer_arguments $llm_credential_args"
installer_arguments="$installer_arguments --bind-address $effective_bind_address --port $effective_anki_port"
installer_arguments="$installer_arguments --app-bind-address $effective_app_bind_address --app-port $effective_app_port"
[ "$reset_anki" = false ] || installer_arguments="$installer_arguments --reset-anki"
[ -z "$effective_timezone" ] || installer_arguments="$installer_arguments --timezone $effective_timezone"
[ "$reset_database" = false ] || installer_arguments="$installer_arguments --reset-database"
[ "$transition" = false ] || installer_arguments="$installer_arguments --transition"
[ "$rebuild" = false ] || installer_arguments="$installer_arguments --rebuild"

if [ "$remote_mode" = helper ]; then
  echo "Streaming and installing with the passwordless Acervo launcher..."
  ssh -T "$target" "sudo -n $helper_path deploy$installer_arguments" <"$archive" || remote_failed
else
  echo "Streaming the Acervo release over SSH as root..."
  ssh -T "$target" "umask 077 && cat > $remote_archive" <"$archive" || remote_failed
  ssh -T "$target" "umask 077 && cat > $remote_installer" <"$repo_root/deploy/acervo/install.sh" || remote_failed
  ssh -T "$target" \
    "sh $remote_installer --archive $remote_archive$installer_arguments; \
     result=\$?; rm -f $remote_installer $remote_archive $remote_credentials $remote_llm_credentials $remote_google_credentials; exit \$result" || remote_failed
fi
remember_sent_dictionaries "$archive"

# The address to open, which is the one thing a deployment summary was not saying. The tailnet
# suffix is a property of the tailnet, not of a machine, so this machine's answer is the server's
# answer — and it is read at the moment it is printed rather than remembered anywhere, because a
# tailnet name is deployment-specific and belongs in no tracked file.
tailnet_suffix() {
  suffix_tool=$(command -v tailscale 2>/dev/null || true)
  for candidate in /Applications/Tailscale.app/Contents/MacOS/Tailscale \
                   /usr/local/bin/tailscale \
                   /var/packages/Tailscale/target/bin/tailscale; do
    [ -z "$suffix_tool" ] || break
    [ ! -x "$candidate" ] || suffix_tool=$candidate
  done
  [ -n "$suffix_tool" ] || return 0
  # `--json` prints one field per line, so this is a line match rather than a parser.
  "$suffix_tool" status --json 2>/dev/null \
    | sed -n 's/.*"MagicDNSSuffix"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' \
    | head -n 1
}

echo "Acervo deployment completed."
if [ -n "$service" ]; then
  suffix=$(tailnet_suffix)
  if [ -n "$suffix" ]; then
    echo "Open Acervo at:        https://$service.$suffix/"
  else
    echo "Open Acervo at:        https://$service.<your tailnet>.ts.net/ (\`tailscale status\` names the suffix)"
  fi
else
  case "${target#*@}" in
    *.ts.net) echo "Open Acervo at:        https://${target#*@}:$effective_https_port/" ;;
    *) echo "Open Acervo at:        https://<the server's tailnet name>:$effective_https_port/" ;;
  esac
fi
echo "Internal HTTP backend: http://$effective_app_bind_address:$effective_app_port"
if [ -n "$service" ]; then
  echo "Dedicated Tailscale service: svc:$service on HTTPS 443 (configure explicitly with ./deploy.sh --configure-https)"
else
  echo "Dedicated Tailscale HTTPS listener: port $effective_https_port (configure explicitly with ./deploy.sh --configure-https)"
fi

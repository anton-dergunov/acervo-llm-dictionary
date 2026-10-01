#!/bin/sh
set -eu

PROTOCOL=13
HELPER_PATH=/usr/local/sbin/deploy-acervo
SUDOERS_PATH=/etc/sudoers.d/deploy-acervo
PATH="$PATH:/usr/sbin:/usr/bin:/sbin:/bin:/usr/local/bin:/var/packages/ContainerManager/target/usr/bin:/var/packages/Docker/target/usr/bin"
export PATH

[ "$(id -u)" -eq 0 ] || {
  echo "deploy-acervo must be installed as a root-owned command and invoked through sudo" >&2
  exit 1
}

validate_port() {
  label=$1
  value=$2
  case "$value" in ''|*[!0-9]*) echo "$label must be numeric" >&2; exit 2 ;; esac
  if [ "$value" -lt 1 ] || [ "$value" -gt 65535 ]; then
    echo "$label must be between 1 and 65535" >&2
    exit 2
  fi
}

install_helper() {
  deployment_user=${SUDO_USER:-}
  [ -n "$deployment_user" ] && [ "$deployment_user" != root ] || {
    echo "Run --install through sudo from the ordinary SSH deployment account" >&2
    exit 2
  }
  id "$deployment_user" >/dev/null 2>&1 || {
    echo "Unknown deployment account" >&2
    exit 2
  }
  mkdir -p /usr/local/sbin /etc/sudoers.d
  install -o root -g root -m 755 "$0" "$HELPER_PATH"
  sudoers_tmp=$(mktemp /etc/sudoers.d/deploy-acervo.XXXXXX)
  trap 'rm -f "$sudoers_tmp"' EXIT HUP INT TERM
  printf '%s ALL=(root) NOPASSWD: %s\n' "$deployment_user" "$HELPER_PATH" >"$sudoers_tmp"
  chown root:root "$sudoers_tmp"
  chmod 440 "$sudoers_tmp"
  if command -v visudo >/dev/null 2>&1; then visudo -cf "$sudoers_tmp" >/dev/null; fi
  mv "$sudoers_tmp" "$SUDOERS_PATH"
  trap - EXIT HUP INT TERM
  echo "Installed passwordless Acervo launcher for the deployment account."
}

docker_path() {
  command -v docker 2>/dev/null || printf '%s\n' /var/packages/ContainerManager/target/usr/bin/docker
}

show_status() {
  docker=$(docker_path)
  "$docker" inspect --format='state={{.State.Status}},health={{.State.Health.Status}}' acervo-anki-sync-server-1
  "$docker" port acervo-anki-sync-server-1 8080
  "$docker" inspect --format='state={{.State.Status}},health={{.State.Health.Status}}' acervo-server-1
  "$docker" port acervo-server-1 8000
}

# One account on the running server. `admin.py accounts create` is the only thing that makes one —
# there is no superuser to have — and it reads the password from stdin, so nothing sensitive reaches a
# command line or this host's process list.
#
# This is a narrower privilege than the launcher already grants: `deploy` extracts an installer out of
# a streamed archive and runs it as root. Running one fixed command in one named container is less
# than that, not more.
create_account() {
  IFS= read -r account_email || { echo "Missing account email address" >&2; exit 2; }
  IFS= read -r account_password || { echo "Missing account password" >&2; exit 2; }
  case "$account_email" in
    *[!A-Za-z0-9@._+-]*|'') echo "Account email address has an implausible shape" >&2; exit 2 ;;
    *@*) ;;
    *) echo "Account email address has an implausible shape" >&2; exit 2 ;;
  esac
  docker=$(docker_path)
  printf '%s\n' "$account_password" | "$docker" exec -i acervo-server-1 \
    python -m acervo.admin accounts create --email "$account_email"
}

# What the deployer asks before it ships a release: how many jobs the running server has open, or
# cancel them. Two fixed commands in one named container, which is less than `deploy` already grants.
# A server that is not running, or predates jobs, answers nothing, and nothing is what that means.
server_jobs() {
  docker=$(docker_path)
  case "$1" in
    open) "$docker" exec acervo-server-1 python -m acervo.admin jobs open --json 2>/dev/null || true ;;
    cancel) "$docker" exec acervo-server-1 python -m acervo.admin jobs cancel --all 2>/dev/null || true ;;
    *) echo "jobs takes open or cancel" >&2; exit 2 ;;
  esac
}

# Spelled out rather than `a-z`: a bracket range follows the locale's collation, and under
# en_GB.UTF-8 `[a-z]` matches capitals too.
validate_service() {
  case "$1" in
    ''|*[!abcdefghijklmnopqrstuvwxyz0123456789-]*)
      echo "Service name must use lowercase letters, digits and hyphens" >&2
      exit 2
      ;;
  esac
}

# A service listener lives on the service's own virtual IP, so 443 here is not the host's 443: it
# cannot collide with another application, with an unrelated Serve mapping, or with a second
# service. That is the whole reason to prefer this over a shared host port -- Android mints a
# WebAPK only for a default port, and two apps separated by port alone collide as one installed
# app. The elaborate guard the port path needs below exists because host ports are shared; a
# service named for Acervo is Acervo's by definition, so this path only has to stay idempotent.
# Services arrived in 1.86.0. An older client rejects --service with a bare "flag provided but not
# defined" and its whole usage screen, which reads like a mistake in this script rather than a
# server that needs updating.
require_service_support() {
  version=$("$tailscale" version 2>/dev/null | head -n 1 | tr -d '\r')
  version=${version%% *}
  major=${version%%.*}
  rest=${version#*.}
  minor=${rest%%.*}
  case "$major.$minor" in
    ''|*[!0-9.]*|.*|*.)
      echo "Could not read the Tailscale version; hosting a service needs 1.86.0 or later" >&2
      exit 1
      ;;
  esac
  if [ "$major" -lt 1 ] || { [ "$major" -eq 1 ] && [ "$minor" -lt 86 ]; }; then
    echo "Tailscale $version cannot host a service; 1.86.0 or later is required." >&2
    echo "Update Tailscale on this server, or publish on a machine port with --https-port." >&2
    exit 1
  fi
}

configure_service_https() {
  require_service_support
  serve_status=$("$tailscale" serve status --json 2>/dev/null || true)
  # A containment check, not a parse: the server may have no JSON parser installed. It can only
  # skip a redundant no-op, so an imprecise match here costs nothing either way.
  case "$serve_status" in
    *"svc:$service"*)
      case "$serve_status" in
        *"$expected_target"*)
          echo "Acervo service mapping already exists; no Tailscale configuration changed."
          return 0
          ;;
      esac
      ;;
  esac

  # --bg is not optional: without it serve runs in the foreground, which over SSH hangs the
  # deployment and discards the mapping the moment the command is interrupted.
  "$tailscale" serve --service="svc:$service" --bg --yes --https=443 "$expected_target"

  updated_status=$("$tailscale" serve status --json 2>/dev/null || true)
  case "$updated_status" in
    *"svc:$service"*) ;;
    *) echo "Tailscale did not report the requested Acervo service" >&2; exit 1 ;;
  esac
  case "$updated_status" in
    *"$expected_target"*) ;;
    *) echo "Tailscale did not report the requested Acervo backend" >&2; exit 1 ;;
  esac
  echo "Configured Acervo only: svc:$service on HTTPS 443 -> $expected_target"
}

configure_https() {
  https_port=
  app_port=
  service=
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --https-port) [ "$#" -ge 2 ] || exit 2; https_port=$2; shift 2 ;;
      --app-port) [ "$#" -ge 2 ] || exit 2; app_port=$2; shift 2 ;;
      --service) [ "$#" -ge 2 ] || exit 2; service=$2; shift 2 ;;
      *) echo "Unsupported configure-https argument: $1" >&2; exit 2 ;;
    esac
  done
  validate_port "App port" "$app_port"

  tailscale=/var/packages/Tailscale/target/bin/tailscale
  [ -x "$tailscale" ] || tailscale=$(command -v tailscale || true)
  [ -n "$tailscale" ] && [ -x "$tailscale" ] || {
    echo "Tailscale is unavailable on this server" >&2
    exit 1
  }
  expected_target="http://127.0.0.1:$app_port"

  if [ -n "$service" ]; then
    validate_service "$service"
    configure_service_https
    return 0
  fi

  validate_port "HTTPS port" "$https_port"
  serve_status=$($tailscale serve status)
  listener=$(printf '%s\n' "$serve_status" | awk -v port="$https_port" '
    /^[a-z]+:\/\// {
      address=$1
      matches=(address ~ (":" port "$"))
      if (port == "443" && address ~ /^https:\/\/[^:]+$/) matches=1
      if (matches) { print; exit }
    }
  ')
  current_target=$(printf '%s\n' "$serve_status" | awk -v port="$https_port" '
    /^[a-z]+:\/\// {
      address=$1
      active=(address ~ (":" port "$"))
      if (port == "443" && address ~ /^https:\/\/[^:]+$/) active=1
      next
    }
    active && /\|-- \/ proxy / { sub(/^.*proxy /, ""); print; exit }
  ')
  if [ -n "$listener" ] && [ "$current_target" != "$expected_target" ]; then
    echo "Refusing to replace the existing listener on port $https_port:" >&2
    printf '%s\n' "$listener" >&2
    [ -z "$current_target" ] || printf '%s\n' "|-- / proxy $current_target" >&2
    exit 1
  fi
  if [ "$current_target" = "$expected_target" ]; then
    echo "Acervo HTTPS mapping already exists; no Tailscale configuration changed."
    return 0
  fi

  "$tailscale" serve --bg --yes --https="$https_port" "$expected_target"
  updated_status=$($tailscale serve status)
  updated_target=$(printf '%s\n' "$updated_status" | awk -v port="$https_port" '
    /^[a-z]+:\/\// {
      address=$1
      active=(address ~ (":" port "$"))
      if (port == "443" && address ~ /^https:\/\/[^:]+$/) active=1
      next
    }
    active && /\|-- \/ proxy / { sub(/^.*proxy /, ""); print; exit }
  ')
  [ "$updated_target" = "$expected_target" ] || {
    echo "Tailscale did not report the requested Acervo mapping" >&2
    exit 1
  }
  echo "Configured Acervo only: HTTPS port $https_port -> $expected_target"
}

deploy_release() {
  acervo_root=
  credentials_file=
  llm_credentials_file=
  google_credentials_file=
  reset_anki=false
  reset_database=false
  transition=false
  timezone=
  bind_address=
  anki_port=
  app_bind_address=
  app_port=
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --root) [ "$#" -ge 2 ] || exit 2; acervo_root=$2; shift 2 ;;
      --credentials-file) [ "$#" -ge 2 ] || exit 2; credentials_file=$2; shift 2 ;;
      --llm-credentials-file) [ "$#" -ge 2 ] || exit 2; llm_credentials_file=$2; shift 2 ;;
      --google-credentials-file) [ "$#" -ge 2 ] || exit 2; google_credentials_file=$2; shift 2 ;;
      --bind-address) [ "$#" -ge 2 ] || exit 2; bind_address=$2; shift 2 ;;
      --port) [ "$#" -ge 2 ] || exit 2; anki_port=$2; shift 2 ;;
      --app-bind-address) [ "$#" -ge 2 ] || exit 2; app_bind_address=$2; shift 2 ;;
      --app-port) [ "$#" -ge 2 ] || exit 2; app_port=$2; shift 2 ;;
      --reset-anki) reset_anki=true; shift ;;
      --timezone) [ "$#" -ge 2 ] || exit 2; timezone=$2; shift 2 ;;
      --reset-database) reset_database=true; shift ;;
      --transition) transition=true; shift ;;
      *) echo "Unsupported deploy argument: $1" >&2; exit 2 ;;
    esac
  done
  case "$acervo_root" in ''|/*/acervo) ;; *) echo "Acervo root must be an absolute path ending in /acervo" >&2; exit 2 ;; esac
  case "$bind_address$app_bind_address" in *[!A-Za-z0-9:._-]*) echo "Unsafe bind address" >&2; exit 2 ;; esac
  case "$timezone" in /*|*/|*[!A-Za-z0-9/_+-]*) echo "Unsafe timezone" >&2; exit 2 ;; esac
  validate_port "Anki port" "$anki_port"
  validate_port "App port" "$app_port"
  [ "$anki_port" != "$app_port" ] || {
    echo "The Acervo app port must differ from the Anki sync port" >&2
    exit 2
  }
  if [ -n "$credentials_file" ]; then
    case "$credentials_file" in /tmp/acervo-credentials-[0-9]*) ;; *) echo "Unexpected credentials path" >&2; exit 2 ;; esac
    [ -f "$credentials_file" ] && [ ! -L "$credentials_file" ] || {
      echo "Missing credentials file" >&2
      exit 2
    }
  fi
  if [ -n "$llm_credentials_file" ]; then
    case "$llm_credentials_file" in /tmp/acervo-llm-credentials-[0-9]*) ;; *) echo "Unexpected LLM credentials path" >&2; exit 2 ;; esac
    [ -f "$llm_credentials_file" ] && [ ! -L "$llm_credentials_file" ] || {
      echo "Missing LLM credentials file" >&2
      exit 2
    }
  fi
  if [ -n "$google_credentials_file" ]; then
    case "$google_credentials_file" in /tmp/acervo-google-credentials-[0-9]*) ;; *) echo "Unexpected Google credentials path" >&2; exit 2 ;; esac
    [ -f "$google_credentials_file" ] && [ ! -L "$google_credentials_file" ] || {
      echo "Missing Google credentials file" >&2
      exit 2
    }
  fi

  private_dir=$(mktemp -d /tmp/acervo-deploy.XXXXXX)
  trap 'rm -rf "$private_dir"; [ -z "${credentials_file:-}" ] || rm -f "$credentials_file"; [ -z "${llm_credentials_file:-}" ] || rm -f "$llm_credentials_file"; [ -z "${google_credentials_file:-}" ] || rm -f "$google_credentials_file"' EXIT HUP INT TERM
  archive="$private_dir/release.tar.gz"
  installer="$private_dir/install.sh"
  chmod 700 "$private_dir"
  cat >"$archive"
  [ -s "$archive" ] || { echo "The Acervo release archive is empty" >&2; exit 2; }
  tar -xOf "$archive" deploy/acervo/install.sh >"$installer" || {
    echo "The release archive has no Acervo installer" >&2
    exit 2
  }
  chmod 700 "$installer"

  set -- --archive "$archive" --bind-address "$bind_address" --port "$anki_port" \
    --app-bind-address "$app_bind_address" --app-port "$app_port"
  [ -z "$acervo_root" ] || set -- "$@" --root "$acervo_root"
  if [ -n "$credentials_file" ]; then
    credentials_copy="$private_dir/credentials"
    cp "$credentials_file" "$credentials_copy"
    chmod 600 "$credentials_copy"
    set -- "$@" --credentials-file "$credentials_copy"
  fi
  if [ -n "$llm_credentials_file" ]; then
    llm_credentials_copy="$private_dir/llm-credentials"
    cp "$llm_credentials_file" "$llm_credentials_copy"
    chmod 600 "$llm_credentials_copy"
    set -- "$@" --llm-credentials-file "$llm_credentials_copy"
  fi
  # Google will not authenticate from a value, so this one credential travels as a file the whole
  # way: streamed to /tmp by the deployer, copied into the private directory here, and installed
  # beside llm.env by the installer for the container to mount.
  if [ -n "$google_credentials_file" ]; then
    google_credentials_copy="$private_dir/google-credentials"
    cp "$google_credentials_file" "$google_credentials_copy"
    chmod 600 "$google_credentials_copy"
    set -- "$@" --google-credentials-file "$google_credentials_copy"
  fi
  [ "$reset_anki" = false ] || set -- "$@" --reset-anki
  [ -z "$timezone" ] || set -- "$@" --timezone "$timezone"
  [ "$reset_database" = false ] || set -- "$@" --reset-database
  [ "$transition" = false ] || set -- "$@" --transition
  sh "$installer" "$@"
}

# The batch worker, run as root without a password so a scheduled job can call it.
#
# On Synology the Docker socket is root-owned and there is no docker group, so reaching the worker
# at all means reaching root. That is worth stating plainly: socket access *is* root access, since
# anything holding it can start a privileged container over the host filesystem. The choice is
# therefore not root versus not-root, but how narrow and reviewable the path to root is — which is
# what this launcher exists to be, and why the answer is a named operation here rather than a
# blanket `NOPASSWD: /usr/bin/docker`.
#
# The operation allow-list stays in `run-worker.sh` rather than being copied here. It already has
# one, a second copy would drift from it, and this is a narrower privilege than the launcher grants
# already: `deploy` extracts an installer out of a streamed archive and runs it as root. What is
# checked here is only that the operation is a bare word, so nothing path-like or flag-like can
# arrive where a subcommand is expected.
# The sample pack: ~3.1 GB of audio, fetched once into the directory the running service actually
# mounts. **That last clause is the whole reason this exists.** The obvious command —
# `docker compose -f compose.yaml run --rm lexibeat lexibeat-bundle fetch …` — omits the deployment's
# env file, so `ACERVO_LEXIBEAT_BUNDLE` is unset, compose falls back to a *named volume*, and the
# bundle unpacks, verifies and reports success into a store nothing serves from. It is a silent
# failure that costs three gigabytes and looks exactly like a success. A bundle the pin no longer
# names is removed by the fetch itself, once the new one has verified, so an upgrade frees its space.
#
# The URL and the digest come from the pin on the calling side, where the repository is: this end
# only checks that they are the shape they should be, so the operation list stays as narrow as the
# rest of it.
install_samples() {
  # Every `--from` is one numbered part of the archive, in order — GitHub refuses a release asset of
  # 2 GiB or more — and each is checked for shape here before any reaches the fetch.
  bundle_from=
  bundle_sha=
  acervo_root=
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --from)
        [ "$#" -ge 2 ] || exit 2
        case "$2" in
          https://github.com/*.tar.[0-9][0-9][0-9]) ;;
          *) echo "install-samples needs https://github.com/… .tar.NNN release part URLs" >&2; exit 2 ;;
        esac
        case "$2" in
          *[!A-Za-z0-9./:_-]*) echo "install-samples: a part URL has an unexpected character" >&2; exit 2 ;;
        esac
        bundle_from="$bundle_from --from $2"; shift 2 ;;
      --sha256) [ "$#" -ge 2 ] || exit 2; bundle_sha=$2; shift 2 ;;
      --root) [ "$#" -ge 2 ] || exit 2; acervo_root=$2; shift 2 ;;
      *) echo "install-samples takes --from (once per part), --sha256 and --root" >&2; exit 2 ;;
    esac
  done
  [ -n "$bundle_from" ] || { echo "install-samples needs at least one --from" >&2; exit 2; }
  case "$bundle_sha" in
    *[!0-9a-f]*|"") echo "install-samples needs a hex sha256" >&2; exit 2 ;;
    *) [ "${#bundle_sha}" -eq 64 ] || { echo "install-samples needs a 64-character sha256" >&2; exit 2; } ;;
  esac

  acervo_root=$(resolve_root "$acervo_root")
  [ -f "$acervo_root/current-release" ] || {
    echo "No deployed release at $acervo_root; deploy before installing the samples" >&2
    exit 2
  }
  IFS= read -r release <"$acervo_root/current-release"
  compose_file="$release/deploy/acervo/compose.yaml"
  [ -f "$compose_file" ] || { echo "The current release has no compose file at $compose_file" >&2; exit 2; }

  docker=$(docker_path)
  set -- -p "${ACERVO_COMPOSE_PROJECT:-acervo}" \
    --env-file "$acervo_root/deployment.env" \
    --env-file "$acervo_root/secrets.env" \
    --env-file "$acervo_root/llm.env" \
    -f "$compose_file"
  echo "Fetching the sample pack — about 3.1 GB, once. It replaces any older one." >&2
  # Unquoted on purpose: it is a list of `--from URL` pairs, each checked above to hold no space or
  # shell metacharacter, so splitting it on spaces is exactly the argument list.
  # shellcheck disable=SC2086
  "$docker" compose "$@" run --rm lexibeat \
    lexibeat-bundle fetch --into /var/lib/lexibeat/bundle \
    $bundle_from --sha256 "$bundle_sha" || exit $?
  # The engine reads the catalogue per request, so a restart is not strictly needed — but the
  # entrypoint's one-line verdict is, and it is printed only at start.
  "$docker" compose "$@" up -d --force-recreate lexibeat >&2 || exit $?
  sleep 2
  "$docker" logs --tail 5 "${ACERVO_COMPOSE_PROJECT:-acervo}-lexibeat-1" 2>&1 | head -5
}

resolve_root() {
  candidate=$1
  if [ -z "$candidate" ]; then
    # The same resolution `run-worker.sh` and the installer use.
    if [ -f /etc/acervo-root ]; then
      IFS= read -r candidate </etc/acervo-root
    elif [ -d /volume1 ]; then
      candidate=/volume1/docker/acervo
    else
      candidate=/opt/acervo
    fi
  fi
  case "$candidate" in /*/acervo) ;; *) echo "Refusing unexpected Acervo root: $candidate" >&2; exit 2 ;; esac
  printf '%s\n' "$candidate"
}

run_worker() {
  acervo_root=
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --root) [ "$#" -ge 2 ] || exit 2; acervo_root=$2; shift 2 ;;
      --) shift; break ;;
      -*) echo "worker takes an operation, not $1" >&2; exit 2 ;;
      *) break ;;
    esac
  done

  if [ -z "$acervo_root" ]; then
    # The same resolution `run-worker.sh` and the installer use, because the script cannot be found
    # without already knowing where it lives.
    if [ -f /etc/acervo-root ]; then
      IFS= read -r acervo_root </etc/acervo-root
    elif [ -d /volume1 ]; then
      acervo_root=/volume1/docker/acervo
    else
      acervo_root=/opt/acervo
    fi
  fi
  case "$acervo_root" in /*/acervo) ;; *) echo "Refusing unexpected Acervo root: $acervo_root" >&2; exit 2 ;; esac

  operation=${1:-}
  case "$operation" in
    "") echo "worker needs an operation, for example anki-pull-state" >&2; exit 2 ;;
    *[!abcdefghijklmnopqrstuvwxyz-]*|-*|*-) echo "worker operations are bare words; got: $operation" >&2; exit 2 ;;
  esac

  [ -f "$acervo_root/current-release" ] || {
    echo "No deployed release at $acervo_root; deploy before running the worker" >&2
    exit 2
  }
  IFS= read -r release <"$acervo_root/current-release"
  script="$release/deploy/acervo/run-worker.sh"
  [ -f "$script" ] || {
    echo "The current release has no worker script at $script" >&2
    exit 2
  }
  sh "$script" --root "$acervo_root" "$@"
}

command_name=${1:-}
case "$command_name" in
  --install) [ "$#" -eq 1 ] || exit 2; install_helper ;;
  check) [ "$#" -eq 1 ] || exit 2; echo "acervo-deploy-protocol: $PROTOCOL" ;;
  status) [ "$#" -eq 1 ] || exit 2; show_status ;;
  configure-https) shift; configure_https "$@" ;;
  create-account) [ "$#" -eq 1 ] || exit 2; create_account ;;
  deploy) shift; deploy_release "$@" ;;
  worker) shift; run_worker "$@" ;;
  install-samples) shift; install_samples "$@" ;;
  jobs) [ "$#" -eq 2 ] || exit 2; server_jobs "$2" ;;
  *) echo "deploy-acervo accepts only check, create-account, deploy, install-samples, jobs, status, worker, or configure-https" >&2; exit 2 ;;
esac

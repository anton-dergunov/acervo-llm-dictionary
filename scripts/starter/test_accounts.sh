#!/bin/sh
# The owner's testing accounts, filled with every starter vocabulary, in one command (laptop):
#
#   scripts/starter/test_accounts.sh [--fresh] [--enrich] [--server URL]
#
# Creates two accounts on the deployed server, if they are not there yet, and installs the zips in
# vocabularies/out/ with the app's own import (web/scripts/install-bundle.ts):
#
#   starters@account.example.com      every starter but Spanish (Spain)
#   starters-es@account.example.com   Spanish (Spain): an account holds one vocabulary per language, and
#                             Spanish (Mexico) is in the first
#
# Both have the password `starters1` (the server's minimum is eight characters). They are testing
# accounts on a server reached only over the tailnet, holding nothing but published vocabularies.
# Sign in as one in a second browser profile: signing out clears a device's copy of the words.
#
# Each account is set, before its first word, to run nothing by itself: no pictures drawn on their
# own, no Anki, no nightly steps, and no per-word `enrich` (`--enrich` queues it, ~500 jobs a
# vocabulary, and a deploy refuses while jobs are open). `--fresh` deletes every word first, so a
# rebuilt starter replaces the one installed before it: an import skips words already held.
#
# The server address is the one `./deploy.sh` prints, from .acervo-deploy and the tailnet, unless
# `--server` names it. Accounts are made by `./deploy.sh --create-account`, so the same target.
set -eu

repo_root=$(CDPATH='' cd -- "$(dirname -- "$0")/../.." && pwd)
out="$repo_root/vocabularies/out"
password=starters1
main_account=starters@account.example.com
spain_account=starters-es@account.example.com
spain_file=acervo-starter-es-ES.zip

server=
install_flags=--testing
while [ "$#" -gt 0 ]; do
  case "$1" in
    --fresh) install_flags="$install_flags --fresh"; shift ;;
    --enrich) install_flags="$install_flags --enrich"; shift ;;
    --server) [ "$#" -ge 2 ] || { echo "--server needs a URL" >&2; exit 2; }; server=$2; shift 2 ;;
    -h|--help) sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $1 (see --help)" >&2; exit 2 ;;
  esac
done

profile_value() {
  [ -f "$repo_root/.acervo-deploy" ] || return 0
  sed -n "s/^$1=//p" "$repo_root/.acervo-deploy" | tail -n 1
}

tailnet_suffix() {
  tool=$(command -v tailscale 2>/dev/null || true)
  [ -n "$tool" ] || [ ! -x /Applications/Tailscale.app/Contents/MacOS/Tailscale ] \
    || tool=/Applications/Tailscale.app/Contents/MacOS/Tailscale
  [ -n "$tool" ] || return 0
  "$tool" status --json 2>/dev/null \
    | sed -n 's/.*"MagicDNSSuffix"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n 1
}

if [ -z "$server" ]; then
  service=$(profile_value ACERVO_SERVICE)
  target=$(profile_value DEPLOY_TARGET)
  if [ -n "$service" ] && suffix=$(tailnet_suffix) && [ -n "$suffix" ]; then
    server="https://$service.$suffix"
  else
    case "${target#*@}" in
      *.ts.net) server="https://${target#*@}:$(profile_value ACERVO_HTTPS_PORT)" ;;
    esac
  fi
  [ -n "$server" ] || { echo "Cannot tell the server's address from .acervo-deploy; pass --server URL" >&2; exit 2; }
fi

ls "$out"/acervo-starter-*.zip >/dev/null 2>&1 || {
  echo "No starter zips in vocabularies/out/. Build them: (cd web && npx tsx scripts/starter-bundle.ts)" >&2
  exit 2
}

create_account() {
  if answer=$(printf '%s\n%s\n' "$1" "$password" | "$repo_root/deploy.sh" --create-account 2>&1); then
    echo "Created $1."
  else
    case "$answer" in
      *"already exists"*) echo "$1 is there already." ;;
      *) printf '%s\n' "$answer" >&2; exit 1 ;;
    esac
  fi
}

install() {
  account=$1
  shift
  # shellcheck disable=SC2086 # the flags are words
  printf '%s\n' "$password" | (cd "$repo_root/web" && npx tsx scripts/install-bundle.ts \
    --server "$server" --email "$account" $install_flags "$@")
}

echo "Server: $server"
create_account "$main_account"
create_account "$spain_account"

main_zips=
for zip in "$out"/acervo-starter-*.zip; do
  [ "$(basename "$zip")" = "$spain_file" ] || main_zips="$main_zips $zip"
done
status=0
# shellcheck disable=SC2086 # the paths have no spaces: they are built from vocabulary ids
install "$main_account" $main_zips || status=$?
if [ -f "$out/$spain_file" ]; then
  install "$spain_account" "$out/$spain_file" || status=$?
fi
exit "$status"

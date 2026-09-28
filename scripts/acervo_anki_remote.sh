#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
target=
acervo_root=

usage() {
  cat >&2 <<'EOF'
usage:
  scripts/acervo_anki_remote.sh [--target USER@HOST] [--root PATH] bootstrap-upload MANIFEST
  scripts/acervo_anki_remote.sh [--target USER@HOST] [--root PATH] push MANIFEST
  scripts/acervo_anki_remote.sh [--target USER@HOST] [--root PATH] export-state
  scripts/acervo_anki_remote.sh [--target USER@HOST] [--root PATH] pull-state
  scripts/acervo_anki_remote.sh [--target USER@HOST] [--root PATH] adopt-server
  scripts/acervo_anki_remote.sh [--target USER@HOST] [--root PATH] push-vocabulary
  scripts/acervo_anki_remote.sh [--target USER@HOST] [--root PATH] bootstrap-vocabulary
EOF
  exit 2
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --target) [ "$#" -ge 2 ] || usage; target=$2; shift 2 ;;
    --root) [ "$#" -ge 2 ] || usage; acervo_root=$2; shift 2 ;;
    bootstrap-upload|push|export-state|pull-state|adopt-server|push-vocabulary|bootstrap-vocabulary) operation=$1; shift; break ;;
    *) usage ;;
  esac
done
[ "${operation:-}" ] || usage

if [ -z "$target" ] && [ -f "$repo_root/.acervo-deploy" ]; then
  IFS= read -r target <"$repo_root/.acervo-deploy"
fi
[ -n "$target" ] || usage
case "$target" in *[!A-Za-z0-9_.@:-]*) echo "Unsafe SSH target" >&2; exit 2 ;; esac
if [ -n "$acervo_root" ]; then
  case "$acervo_root" in /*/acervo) ;; *) echo "Root must be an absolute path ending in /acervo" >&2; exit 2 ;; esac
  case "$acervo_root" in *[!A-Za-z0-9_./-]*) echo "Unsafe Acervo root" >&2; exit 2 ;; esac
fi

manifest=
case "$operation" in
  bootstrap-upload|push)
    [ "$#" -eq 1 ] || usage
    manifest=$1
    [ -f "$manifest" ] || { echo "Manifest not found: $manifest" >&2; exit 2; }
    ;;
  *) [ "$#" -eq 0 ] || usage ;;
esac

temporary_dir=$(mktemp -d "${TMPDIR:-/tmp}/acervo-anki-remote.XXXXXX")
remote_helper="/tmp/acervo-run-worker-$$.sh"
remote_input="/tmp/acervo-anki-input-$$.tar.gz"
cleanup() {
  status=$?
  trap - EXIT
  rm -rf -- "$temporary_dir"
  ssh -T "$target" "rm -f $remote_helper $remote_input" >/dev/null 2>&1 || true
  exit "$status"
}
trap cleanup EXIT HUP INT TERM

ssh -T "$target" "umask 077 && cat > $remote_helper" \
  <"$repo_root/deploy/acervo/run-worker.sh"

helper_arguments=
if [ -n "$acervo_root" ]; then
  helper_arguments="--root $acervo_root"
fi
if [ -n "$manifest" ]; then
  input_archive="$temporary_dir/input.tar.gz"
  python_runner=${PYTHON:-python3}
  if [ -x "$repo_root/.venv/bin/python" ]; then
    python_runner="$repo_root/.venv/bin/python"
  fi
  "$python_runner" "$repo_root/scripts/package_anki_sync_input.py" \
    "$manifest" "$input_archive"
  ssh -T "$target" "umask 077 && cat > $remote_input" <"$input_archive"
  helper_arguments="$helper_arguments --input-archive $remote_input"
fi

echo "Running Acervo Anki $operation on the remote server..."
ssh -t "$target" \
  "if [ \"\$(id -u)\" -eq 0 ]; then run=sh; else run='sudo sh'; fi; \
   \$run $remote_helper $helper_arguments $operation; \
   status=\$?; rm -f $remote_helper $remote_input; exit \$status"

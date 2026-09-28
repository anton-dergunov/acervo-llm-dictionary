#!/bin/sh
set -eu

PATH="$PATH:/usr/local/bin:/var/packages/ContainerManager/target/usr/bin:/var/packages/Docker/target/usr/bin"
export PATH

usage() {
  echo "usage: run-worker.sh [--root PATH] {anki-bootstrap-vocabulary|anki-push-vocabulary|anki-pull-state" >&2
  echo "         |anki-export-state|anki-adopt-server}" >&2
  echo "       run-worker.sh [--root PATH] --input-archive FILE {anki-bootstrap-upload|anki-push}" >&2
  echo "       run-worker.sh [--root PATH] build-dictionary <compiler arguments...>" >&2
  echo "         e.g. build-dictionary --id cc-cedict" >&2
  echo "              build-dictionary --all --language es,en,zh" >&2
  echo "       run-worker.sh [--root PATH] backfill <arguments...>" >&2
  echo "         e.g. backfill --owner-email learner@account.example.com --limit 50" >&2
  echo "              backfill --owner-email learner@account.example.com --language es --dry-run" >&2
  exit 2
}

acervo_root=
input_archive=
while [ "$#" -gt 0 ]; do
  case "$1" in
    --root) [ "$#" -ge 2 ] || usage; acervo_root=$2; shift 2 ;;
    --input-archive) [ "$#" -ge 2 ] || usage; input_archive=$2; shift 2 ;;
    anki-bootstrap-vocabulary|anki-push-vocabulary|anki-pull-state|anki-export-state|anki-adopt-server|anki-bootstrap-upload|anki-push|build-dictionary|backfill) operation=$1; shift; break ;;
    *) usage ;;
  esac
done
[ "${operation:-}" ] || usage
# The compiler's own flags are passed straight through, so building one dictionary and building
# every Spanish one are the same command with different arguments rather than two wrappers.
if [ "$operation" = build-dictionary ] || [ "$operation" = backfill ]; then
  [ "$#" -ge 1 ] || usage
else
  [ "$#" -eq 0 ] || usage
fi

if [ -z "$acervo_root" ]; then
  if [ -f /etc/acervo-root ]; then
    IFS= read -r acervo_root </etc/acervo-root
  elif [ -d /volume1 ]; then
    acervo_root=/volume1/docker/acervo
  else
    acervo_root=/opt/acervo
  fi
fi
case "$acervo_root" in
  /*/acervo) ;;
  *) echo "Refusing unexpected Acervo root: $acervo_root" >&2; exit 2 ;;
esac

if docker compose version >/dev/null 2>&1; then
  compose() { docker compose "$@"; }
elif command -v docker-compose >/dev/null 2>&1; then
  compose() { docker-compose "$@"; }
else
  echo "Docker Compose is unavailable" >&2
  exit 1
fi

release=$(cat "$acervo_root/current-release")
compose_file="$release/deploy/acervo/compose.yaml"
# `--build` on every run, because a deployment builds only the two long-running services: the worker
# is a `profiles: ["tools"]` container that exists to be `run`, so nothing else ever rebuilds it and
# a job would quietly execute whatever code the last build happened to contain. The layers cache, so
# an unchanged release costs a second.
common_args="-p acervo --env-file $acervo_root/deployment.env --env-file $acervo_root/secrets.env --env-file $acervo_root/llm.env -f $compose_file"

input_dir=
cleanup() {
  status=$?
  trap - EXIT
  if [ -n "$input_dir" ]; then
    case "$input_dir" in "$acervo_root/input/runs/"*) rm -rf -- "$input_dir" ;; esac
  fi
  exit "$status"
}
trap cleanup EXIT HUP INT TERM

case "$operation" in
  anki-bootstrap-upload|anki-push)
    # A manifest carried in from outside, which is what the sync smoke test drives. The robot runs
    # in the worker for these, against the same collection and lock the server uses.
    [ -f "$input_archive" ] || { echo "$operation requires an input archive" >&2; exit 2; }
    run_id=$(date -u +%Y%m%dT%H%M%SZ)-$$
    input_dir="$acervo_root/input/runs/$run_id"
    mkdir -p "$input_dir"
    tar -xzf "$input_archive" -C "$input_dir"
    # shellcheck disable=SC2086
    compose $common_args --profile tools run --rm --build acervo-worker \
      anki "${operation#anki-}" "/input/runs/$run_id/manifest.json"
    ;;
  anki-bootstrap-vocabulary|anki-push-vocabulary|anki-pull-state|anki-export-state|anki-adopt-server)
    # The vocabulary's own Anki work runs in the server, which holds the vocabulary, the pictures and
    # the robot's collection, and which runs the same push and read by itself: after a change, and
    # every hour. These do it now, by hand, and print what they do.
    case "$operation" in
      anki-bootstrap-vocabulary) command=bootstrap ;;
      anki-push-vocabulary) command=push ;;
      anki-pull-state) command=pull ;;
      anki-export-state) command=export-state ;;
      anki-adopt-server) command=adopt-server ;;
    esac
    # shellcheck disable=SC2086
    compose $common_args exec -T server python -m acervo.admin anki "$command"
    ;;
  build-dictionary)
    # Compiling streams sources that run to gigabytes, so this is deliberately a command the owner
    # runs rather than something a checkbox triggers.
    # shellcheck disable=SC2086
    compose $common_args --profile tools run --rm --build acervo-worker dictionary build "$@"
    ;;
  backfill)
    # The corner case the event-driven design leaves: words that existed before it, or an import
    # that asked for nothing. It queues the same `enrich` job a save queues, so it is not a second
    # pipeline — and it runs in the *server*, which is what holds the database and the runner.
    # shellcheck disable=SC2086
    compose $common_args exec -T server \
      python -m acervo.admin jobs enqueue enrich --missing "$@"
    ;;
esac

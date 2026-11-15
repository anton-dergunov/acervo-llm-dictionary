#!/usr/bin/env bash
# The whole full run in one command (README, "The full run"): Argon fact-checks g1's scripts, g1 is
# drawn while Argon writes g2 and g3, those are checked, then drawn. Every step skips what is done
# and no job is ever submitted twice, so it is safe to stop (Ctrl-C) and rerun at any time.
#
# It bills only the account billing.local.json names, and checks that here (profile, gcloud account
# and project) before Python checks it again on every request; it spends at most that file's `cap`,
# counting what was spent and what is in flight.
#
# Run from the repository root, after `gcp use <profile>`:
#   caffeinate -i experiments/character-pictures/full_run.sh 2>&1 | tee -a experiments/character-pictures/out/full/full.log
# Options go to `run.py full`: --takes 6 (the default), --takes-for g1=8, --dry-run, --poll 300.
set -euo pipefail
cd "$(dirname "$0")/../.."
PY=.venv/bin/python
HERE=experiments/character-pictures
BILLING=$HERE/billing.local.json

stop() { echo "STOPPED: $*"; exit 1; }
[ -f "$BILLING" ] || stop "no $BILLING naming the one account this run may bill"
field() { "$PY" -c "import json, sys; print(json.load(open(sys.argv[1])).get(sys.argv[2]) or '')" "$BILLING" "$1"; }
PROJECT=$(field project)
ACCOUNT=$(field account)
PROFILE=$(field profile)
[ -n "$PROJECT" ] && [ -n "$ACCOUNT" ] && [ -n "$(field cap)" ] || stop "$BILLING needs project, account and cap"

[ -z "$PROFILE" ] || [ "${GCP_PROFILE:-}" = "$PROFILE" ] \
  || stop "the shell's profile is ${GCP_PROFILE:-not set}; run \`gcp use $PROFILE\` first"
[ -n "${GOOGLE_APPLICATION_CREDENTIALS:-}" ] \
  || stop "GOOGLE_APPLICATION_CREDENTIALS is not set; run \`gcp use ${PROFILE:-<profile>}\` first"
[ "$(gcloud config get-value account 2>/dev/null)" = "$ACCOUNT" ] \
  || stop "gcloud's active account is not the one $BILLING names"
[ "$(gcloud config get-value project 2>/dev/null)" = "$PROJECT" ] \
  || stop "gcloud's active project is not the one $BILLING names"
[ -z "${GOOGLE_CLOUD_PROJECT:-}" ] || [ "$GOOGLE_CLOUD_PROJECT" = "$PROJECT" ] \
  || stop "GOOGLE_CLOUD_PROJECT names another project"
echo "account checked: profile ${PROFILE:-any}, gcloud account and project as $BILLING names"

"$PY" "$HERE/run.py" origins --set common
exec "$PY" "$HERE/run.py" full "$@"

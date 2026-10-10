#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
# Where the archive lands. Overridable, and the reason is a deployment that failed for it: the path
# used to be fixed at `build/acervo-server.tar.gz`, so the deployment tests rewrote the very file a
# concurrent `./deploy.sh` was streaming. The remote saw a valid gzip stream with another process's
# bytes appended, reported "trailing garbage" and a tar child status 2, and gave up with "the
# release archive has no Acervo installer" — a failure with nothing in it pointing at the cause.
# Tests pass a path of their own; a real deploy keeps the default.
archive=${ACERVO_PACKAGE_ARCHIVE:-"$repo_root/build/acervo-server.tar.gz"}
output_dir=$(dirname -- "$archive")
temporary=$(mktemp -d "${TMPDIR:-/tmp}/acervo-server-package.XXXXXX")
bundle="$temporary/release"
trap 'rm -rf "$temporary"' EXIT HUP INT TERM

if [ ! -f "$repo_root/deploy/acervo/server/web/manifest.webmanifest" ]; then
  echo "Staged Acervo PWA is missing. Run npm run stage:pwa first." >&2
  exit 1
fi

eval "$("$repo_root/scripts/version.sh")"
mkdir -p "$output_dir" "$bundle"
for directory in config deploy dictionaries docs models prompts requirements scripts src templates; do
  mkdir -p "$bundle/$directory"
  rsync -a --exclude .DS_Store --exclude __pycache__ --exclude '*.pyc' --exclude 'llm.env' \
    "$repo_root/$directory/" "$bundle/$directory/"
done
# The server image installs the package from the bundle, so its build files travel too.
cp "$repo_root/package.json" "$repo_root/pyproject.toml" "$repo_root/README.md" "$bundle/"

cat >"$bundle/version.json" <<EOF
{ "version": "$ACERVO_APP_VERSION", "build": "$ACERVO_APP_BUILD" }
EOF

if [ "${ACERVO_INCLUDE_MACOS_RELEASE:-false}" = true ] && [ -f "$repo_root/build/macos-release/release.json" ]; then
  release_version=$(sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$repo_root/build/macos-release/release.json" | head -n 1)
  release_build=$(sed -n 's/.*"build"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$repo_root/build/macos-release/release.json" | head -n 1)
  if [ "$release_version" != "$ACERVO_APP_VERSION" ] || [ "$release_build" != "$ACERVO_APP_BUILD" ]; then
    echo "The macOS release does not match the server version/build; package the coordinated release again" >&2
    exit 1
  fi
  mkdir -p "$bundle/downloads"
  cp -R "$repo_root/build/macos-release/." "$bundle/downloads/"
fi

# Compiled dictionaries are built on the machine that runs the compiler and are not in the
# repository, so they travel in the release the way the macOS application does. This is a private
# copy moving between the owner's own machines; the licensing rule in docs §9 is about publishing to
# the world and does not apply.
dictionary_artifacts=${ACERVO_DICTIONARY_ARTIFACTS:-"$repo_root/data/dictionaries/out"}
# What the server will hold once this archive is installed, as one checksum line per file, written
# beside the archive for the deployer to keep. `ACERVO_DICTIONARIES_SENT` names the one it kept last
# time: a dictionary whose three lines are all in it is already on the server and is left out, which
# is safe because the installer merges a release's dictionaries into the published ones rather than
# replacing them. Unset, or naming nothing, every dictionary travels.
dictionary_manifest="$archive.dictionaries"
dictionaries_sent=${ACERVO_DICTIONARIES_SENT:-}
rm -f "$dictionary_manifest"
if [ "${ACERVO_INCLUDE_DICTIONARIES:-true}" = true ] && [ -d "$dictionary_artifacts" ] \
   && [ -n "$(find "$dictionary_artifacts" -maxdepth 1 -name '*.json' -print -quit)" ]; then
  mkdir -p "$bundle/dictionary-artifacts"
  : >"$dictionary_manifest"
  unchanged=0
  # Only complete triples: a `.json` with no payload beside it would be listed by the server and
  # then fail at the moment someone tried to store it.
  for metadata in "$dictionary_artifacts"/*.json; do
    id=$(basename "$metadata" .json)
    if [ -f "$dictionary_artifacts/$id.dict" ] && [ -f "$dictionary_artifacts/$id.idx" ]; then
      checksums=$(cd "$dictionary_artifacts" && cksum "$id.json" "$id.dict" "$id.idx")
      printf '%s\n' "$checksums" >>"$dictionary_manifest"
      if [ -n "$dictionaries_sent" ] && [ -f "$dictionaries_sent" ] \
         && [ -z "$(printf '%s\n' "$checksums" | grep -Fxv -f "$dictionaries_sent" || true)" ]; then
        unchanged=$((unchanged + 1))
        continue
      fi
      cp "$metadata" "$dictionary_artifacts/$id.dict" "$dictionary_artifacts/$id.idx" \
        "$bundle/dictionary-artifacts/"
    else
      echo "Skipping incomplete dictionary $id (no .dict/.idx beside its metadata)" >&2
    fi
  done
  bundled=$(find "$bundle/dictionary-artifacts" -name '*.json' | wc -l | tr -d ' ')
  # stderr, not stdout: this script's stdout is the archive path and deploy.sh reads it.
  if [ "$bundled" -eq 0 ]; then
    rmdir "$bundle/dictionary-artifacts"
    echo "All $unchanged compiled dictionaries are already on the server; sending none (--rebuild sends them again)." >&2
  else
    size=$(du -sh "$bundle/dictionary-artifacts" | cut -f1)
    if [ "$unchanged" -gt 0 ]; then
      echo "Bundling $bundled changed compiled dictionaries ($size); $unchanged are already on the server." >&2
    else
      echo "Bundling $bundled compiled dictionaries ($size). Set ACERVO_INCLUDE_DICTIONARIES=false to skip." >&2
    fi
  fi
fi

# The pinned spoken-usage-retrieval wheel. It is not in the repository — deploy/acervo/speech/pin.json
# names it and scripts/fetch_speech.sh downloads it — but compose builds the speech image with the
# repository root as its context, and on the server that root is this extracted archive. A release
# without the wheel produces a deployment that cannot build, so this is required rather than
# optional, unlike the compiled dictionaries above.
#
# Only the wheel: the npm tarball is consumed by `npm --prefix web run build` on the machine cutting
# the release, and what ships from that is the staged interface under deploy/acervo/server/web.
# Named by the pin rather than found by a glob. `find … -print -quit` takes whichever wheel it
# reaches first, so a leftover from a previous version could be packaged instead of the pinned one
# — and the archive would deploy a service the pin does not describe, with nothing saying so.
speech_wheel="$repo_root/vendor/speech/$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["artifacts"]["wheel"]["file"])' "$repo_root/deploy/acervo/speech/pin.json")"
if [ ! -f "$speech_wheel" ]; then
  echo "Missing the pinned spoken-usage-retrieval wheel: ${speech_wheel##*/}" >&2
  echo "Run scripts/fetch_speech.sh first; the speech service cannot be built without it." >&2
  exit 1
fi
mkdir -p "$bundle/vendor/speech"
cp "$speech_wheel" "$bundle/vendor/speech/"

# The pinned lexibeat wheel, on the same terms and for the same reason: compose builds the loop
# service from the extracted archive, so a release without it deploys a service that cannot build.
#
# Only the wheel. The ~3.1 GB sample bundle the same pin names is deliberately *not* here: it is
# fetched once on the server into a volume, and putting three gigabytes of audio into every release
# archive to save one command would be the opposite trade to the one the dictionaries make, which
# are small enough to ride along.
lexibeat_wheel="$repo_root/vendor/lexibeat/$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["artifacts"]["wheel"]["file"])' "$repo_root/deploy/acervo/lexibeat/pin.json")"
if [ ! -f "$lexibeat_wheel" ]; then
  echo "Missing the pinned lexibeat wheel: ${lexibeat_wheel##*/}" >&2
  echo "Run scripts/fetch_lexibeat.sh first; the loop service cannot be built without it." >&2
  exit 1
fi
mkdir -p "$bundle/vendor/lexibeat"
cp "$lexibeat_wheel" "$bundle/vendor/lexibeat/"

archive_entries="config deploy dictionaries docs models prompts requirements scripts src templates package.json pyproject.toml README.md version.json vendor"
[ ! -d "$bundle/downloads" ] || archive_entries="$archive_entries downloads"
[ ! -d "$bundle/dictionary-artifacts" ] || archive_entries="$archive_entries dictionary-artifacts"

if [ "$(uname -s)" = Darwin ]; then
  COPYFILE_DISABLE=1 tar --no-xattrs --no-mac-metadata -C "$bundle" -czf "$archive" \
    $archive_entries
else
  tar -C "$bundle" -czf "$archive" $archive_entries
fi

printf '%s\n' "$archive"

# The spoken-usage-retrieval service, from the wheel pinned in pin.json beside this file.
#
# The image is Acervo's rather than that repository's, which is what its own contract asks for: the
# package never self-daemonizes, and process supervision, volumes, the URL and credentials are the
# host's. That also keeps the base image, the user and the healthcheck under the rules this
# deployment already lives by. See docs/features/spoken-clips.md §2.1–§2.3.
#
# The wheel reaches the build context through vendor/speech/, which scripts/fetch_speech.sh fills
# and scripts/package_acervo_server.sh carries into the release archive — the server builds from
# the extracted release, so an artifact that is not in the archive is not in the build context.
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Both defaults in the package are *relative* paths, which in a container means "wherever the
    # working directory happens to be". They must be set explicitly or the service quietly builds
    # its corpus somewhere that is not a mount.
    SPEECH_RETRIEVAL_DATA_DIR=/var/lib/speech/data \
    SPEECH_RETRIEVAL_CATALOGUE_DIR=/var/lib/speech/catalogues \
    SPEECH_RETRIEVAL_HOST=0.0.0.0 \
    SPEECH_RETRIEVAL_PORT=8000

WORKDIR /app

# No ffmpeg and no ffprobe: they are needed only by the optional audio path, which is off by
# default, and yt-dlp is reached as a Python module rather than as a system binary. No Stanza
# either — `analyzer=auto` falls back to simplemma and never downloads a model implicitly.
COPY vendor/speech/*.whl /tmp/wheels/
RUN pip install --no-cache-dir /tmp/wheels/*.whl && rm -rf /tmp/wheels

# The player's target text runs on the *owner's* chain rather than on a key this service holds, so
# this image carries `acervo.models` and the catalogue that names the providers — and nothing else
# of Acervo's. `create_app` takes both providers as arguments, which is a public entry point of that
# package, so the retrieval repository changes nothing: no LiteLLM dependency, no schema-dialect
# port, no error-taxonomy mapping. See docs/features/spoken-clips.md §2.13.
#
# Acervo's *server* image still never imports `speech_retrieval`, and this one never imports
# Acervo's graph, settings or database.
# Laid out as `/app/src/acervo/...` beside `/app/models`, which is exactly the server image's
# shape — and it has to be, because `CATALOGUE_PATH` is resolved relative to the module's own file
# (`parents[3] / "models" / "catalogue.json"`). Installing the package into site-packages instead
# put the catalogue somewhere that does not exist, and the only symptom was no provider being
# injected, silently.
COPY src/acervo/__init__.py /app/src/acervo/__init__.py
COPY src/acervo/access_log.py /app/src/acervo/access_log.py
COPY src/acervo/models /app/src/acervo/models
COPY src/acervo/speech /app/src/acervo/speech
COPY models /app/models
ENV PYTHONPATH=/app/src
# `google-auth` is not optional here even though LiteLLM does not require it. Vertex is the one
# provider that authenticates from a file, and LiteLLM reaches it with a deferred
# `import google.auth` — so without this the row looks perfectly available (a catalogue row is
# checked for environment variables and a credentials file, never for an importable library) and
# raises on the first real call. The server image gets it for free through `google-genai`; this one
# installs LiteLLM alone and got nothing. The `[requests]` extra is what supplies
# `google.auth.transport.requests`, LiteLLM itself depending on httpx.
RUN pip install --no-cache-dir "litellm>=1.100" "google-auth[requests]>=2"

# `data` holds two very different things and they are mounted separately: `raw/` is acquired
# captions, which cost bandwidth and are the one thing here nothing may delete, while `index/` and
# `derived/` are rebuilt from it. `catalogues/` is the operator's channel list.
RUN mkdir -p /var/lib/speech/data/raw /var/lib/speech/data/index \
             /var/lib/speech/data/derived /var/lib/speech/data/reports \
             /var/lib/speech/catalogues \
    && chmod -R a+rX /app \
    && chmod -R a+rwX /var/lib/speech

# Seeding is not a convenience. An empty catalogue directory cannot be filled through the API —
# the repository only rewrites a `<language>.json` that already exists, and the schema rejects a
# catalogue with no sections — so a fresh mount would leave channel management with nothing to
# edit. `channels seed` never overwrites, which is why this can run unconditionally on every start
# rather than behind a test the entrypoint would have to get right.
COPY deploy/acervo/speech/entrypoint.sh /usr/local/bin/speech-entrypoint
COPY deploy/acervo/speech/serve.py /app/serve.py
# `a+rx`, not `+x`: a bare `+x` is masked by the umask, and the installer extracts a release under
# `umask 077`, so the copied file arrives owner-only and stays that way. The container runs as the
# deploying user against a root-owned file and cannot open its own entry point — which reads as
# "Permission denied" from `/bin/sh` with nothing pointing at the cause.
RUN chmod a+rx /usr/local/bin/speech-entrypoint && chmod -R a+rX /app

EXPOSE 8000
ENTRYPOINT ["/usr/local/bin/speech-entrypoint"]
# Acervo's own entry point rather than the console script, so `create_app` is called with the
# owner's chain behind both provider stages. With no chain and no credential it injects neither and
# the service behaves exactly as `speech-retrieval serve` would.
CMD ["python", "/app/serve.py"]

# Pinned by digest, in all four Dockerfiles alike. The tag moves whenever upstream republishes it —
# three times in three weeks — and a build that follows it throws away every layer below, reinstalling
# what had not changed. Upgrading the base is editing this digest, in all four
# (docs/operations/deployment.md, "What a deploy rebuilds").
#
# Two stages, because two services are built from this file and only one of them runs Acervo's code.
# The sync server is `python -m anki.syncserver` and nothing else, so it stops at the first stage: a
# code change neither rebuilds nor restarts it.
FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258 AS sync-server

ARG ANKI_VERSION=26.8.1

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

# PyGlossary is pinned and lxml is explicit: without lxml it silently disables seven plugins,
# including the CC-CEDICT reader, warning rather than failing (docs §11.4). Pillow scales pictures
# down for the Anki cards; it is imported only when a push writes them, so nothing fails earlier.
RUN python -m pip install --no-cache-dir \
    "anki==${ANKI_VERSION}" \
    "httpx>=0.28" \
    "pydantic>=2,<3" \
    "python-slugify>=8,<9" \
    "pyglossary==5.4.2" \
    "lxml" \
    "pillow>=12.3"

RUN mkdir -p /var/lib/acervo/anki-server /var/lib/acervo/worker /var/lib/acervo/dictionaries /input

WORKDIR /app
EXPOSE 8080

FROM sync-server AS worker

# `--chmod` on every `COPY`: the installer extracts a release under `umask 077`, so the files this
# image is built from are owner-only — and `COPY` makes them root-owned. The container runs as the
# deploying user, which then cannot read its own entry point: "can't open file
# '/app/scripts/acervo_worker.py'". Ordered rarest change first, with nothing run after them, so a
# code change rebuilds as few layers as it can.
COPY --chmod=755 templates /app/templates
COPY --chmod=755 dictionaries /app/dictionaries
# The provider catalogue. LiteLLM itself is deliberately not installed here: no worker job
# calls a model yet, and `acervo.models` imports it lazily so `acervo.models.pacing` — which
# the file ingestion uses — works without it.
COPY --chmod=755 models /app/models
COPY --chmod=755 scripts/integration/anki_sync_client.py /app/scripts/integration/anki_sync_client.py
COPY --chmod=755 scripts/acervo_worker.py /app/scripts/acervo_worker.py
COPY --chmod=755 src /app/src

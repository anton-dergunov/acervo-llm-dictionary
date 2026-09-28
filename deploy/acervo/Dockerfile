FROM python:3.12-slim-bookworm

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

WORKDIR /app
COPY src /app/src
COPY dictionaries /app/dictionaries
# The provider catalogue. LiteLLM itself is deliberately not installed here: no worker job
# calls a model yet, and `acervo.models` imports it lazily so `acervo.models.pacing` — which
# the file ingestion uses — works without it.
COPY models /app/models
COPY scripts/acervo_worker.py /app/scripts/acervo_worker.py
COPY scripts/integration/anki_sync_client.py /app/scripts/integration/anki_sync_client.py
COPY templates /app/templates

# The installer extracts a release under `umask 077`, so the files this image is built from are
# owner-only — and `COPY` makes them root-owned. The container runs as the deploying user, which
# then cannot read its own entry point: "can't open file '/app/scripts/acervo_worker.py'". The
# server image has always done this; the worker never needed to until a job here started writing.
RUN chmod -R a+rX /app

RUN mkdir -p /var/lib/acervo/anki-server /var/lib/acervo/worker /var/lib/acervo/dictionaries /input

EXPOSE 8080

# Pinned by digest, in all four Dockerfiles alike. The tag moves whenever upstream republishes it —
# three times in three weeks — and a build that follows it throws away every layer below, reinstalling
# what had not changed. Upgrading the base is editing this digest, in all four
# (docs/operations/deployment.md, "What a deploy rebuilds").
FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ACERVO_DB_PATH=/var/lib/acervo/server/acervo.db \
    ACERVO_WEB_PATH=/app/web \
    ACERVO_PROMPTS_PATH=/app/prompts \
    ACERVO_DOWNLOADS_PATH=/var/lib/acervo/downloads \
    ACERVO_DICTIONARIES_PATH=/var/lib/acervo/dictionaries

WORKDIR /app

# The meaning map's encoder runs on torch, and the default wheel carries CUDA libraries a NAS has no
# use for; the CPU-only build is a fraction of the size, so it goes in first and the requirements
# below find it already satisfied.
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch

COPY requirements /app/requirements
RUN pip install --no-cache-dir -r requirements/server.txt

# The Anki robot, which pushes the vocabulary to the sync server and reads review state back. The
# sync protocol is version-locked, so this carries the sync server's own pin as the same build
# argument, and the two are upgraded as a pair.
ARG ANKI_VERSION=26.8.1
RUN pip install --no-cache-dir "anki==${ANKI_VERSION}"

# The encoder's weights, at the revision `models/encoder.json` pins, fetched once at build time and
# before `src` is copied, so a code change never downloads them again. Only the files
# sentence-transformers reads: the repository also carries ONNX and OpenVINO copies nobody here uses.
# At run time the library is told it is offline, so drawing a map never reaches the network.
ENV HF_HOME=/opt/huggingface
COPY models/encoder.json /app/models/encoder.json
RUN python -c "import json; from huggingface_hub import snapshot_download; \
pin = json.load(open('/app/models/encoder.json')); \
snapshot_download(pin['model'], revision=pin['revision'], allow_patterns=pin['files'])" \
    && chmod -R a+rX /opt/huggingface
# Photo capture's sentence splitter, Segment any Text, at the revisions `models/segmenter.json` pins:
# the ONNX model and the tokenizer it reads with. ~400 MB, loaded only once somebody opens the Photo
# tab, and read file by file at run time because the hub is offline by then.
COPY models/segmenter.json /app/models/segmenter.json
RUN python -c "import json; from huggingface_hub import hf_hub_download; \
pin = json.load(open('/app/models/segmenter.json')); \
[hf_hub_download(one['model'], name, revision=one['revision']) \
 for one in (pin, pin['tokenizer']) for name in one['files']]" \
    && chmod -R a+rX /opt/huggingface
ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    NUMBA_CACHE_DIR=/tmp/numba

RUN mkdir -p /var/lib/acervo/server /var/lib/acervo/downloads /var/lib/acervo/dictionaries \
    /var/lib/acervo/worker \
    && chmod -R a+rwX /var/lib/acervo

# **Everything below is ordered by how often it changes, rarest first**, and nothing runs after it.
# A layer is rebuilt when anything above it changed, and on the NAS each rebuilt layer costs seconds
# whatever its size — so a code change rebuilds the last two and a prompt change three. A step
# placed after `src` would be rebuilt, and paid for, on every deploy.
#
# `--chmod` on every `COPY` rather than one `chmod -R` at the end, which would be such a step. It is
# not optional: the installer extracts a release under `umask 077`, so the files this image is built
# from are owner-only, and `COPY` makes them root-owned. The container runs as the deploying user,
# which then cannot read its own code.

# The provider catalogue, beside `src` the way `dictionaries/` is: the package resolves it
# relative to itself, so it needs no environment variable and no staging step.
COPY --chmod=755 models /app/models
# The style table is content of the same kind, and `acervo.images.styles` resolves it relative to
# the package exactly as the two catalogues above do — hence the matching path rather than a third
# environment variable.
COPY --chmod=755 config/image-styles.yaml /app/config/image-styles.yaml
COPY --chmod=755 config/story-types.yaml /app/config/story-types.yaml
# The Anki cards' faces, stylesheet, script and fonts, which every push brings up to date.
COPY --chmod=755 templates /app/templates
# The capture prompts are content, not code: tracked once at the repository root and read at request
# time, so changing what an entry says never means changing the code that builds a request.
COPY --chmod=755 prompts /app/prompts
# On the path rather than installed, as in the worker and corpus images: an editable install is a
# step after `src` that fetches a build backend from the network in order to write one path file.
ENV PYTHONPATH=/app/src
COPY --chmod=755 src /app/src
# The built interface. `.dockerignore` excludes `web/dist`, so `scripts/stage-web.sh` is what puts it
# somewhere a build context can see.
COPY --chmod=755 deploy/acervo/server/web /app/web

EXPOSE 8000
CMD ["python", "-m", "acervo.admin", "serve", "--host", "0.0.0.0", "--port", "8000"]

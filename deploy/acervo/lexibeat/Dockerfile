# The LexiBeat loop generator, from the wheel pinned in pin.json beside this file.
#
# The image is Acervo's rather than that repository's, which is what its own contract asks for: the
# package never self-daemonizes, and process supervision, volumes, the URL and credentials are the
# host's. See docs/features/loops.md §2.1–§2.3.
#
# **This is the one companion image that carries no provider credential at all**, and its absence is
# the design rather than an oversight. LexiBeat is handed a voice: `serve.py` implements its
# `Backend` protocol as a call *home* to `POST /pronunciations/take`, carrying a render-scoped token
# that lives in the process and nowhere else. So there is no `acervo.models` here, no
# `models/catalogue.json`, and no key of any kind — one rate limiter, one cooldown, one call log, one
# place the owner chooses, all of them on the server. `test_deployment.py` asserts this absence.
#
# The wheel reaches the build context through vendor/lexibeat/, which scripts/fetch_lexibeat.sh fills
# and scripts/package_acervo_server.sh carries into the release archive — the server builds from the
# extracted release, so an artifact that is not in the archive is not in the build context.
# Pinned by digest, in all four Dockerfiles alike. The tag moves whenever upstream republishes it —
# three times in three weeks — and a build that follows it throws away every layer below, reinstalling
# what had not changed. Upgrading the base is editing this digest, in all four
# (docs/operations/deployment.md, "What a deploy rebuilds").
FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Where finished tracks are written before Acervo fetches them. A mount, not the image.
    LEXIBEAT_SERVICE_OUT=/var/lib/lexibeat/out \
    LEXIBEAT_SERVICE_QUEUE=4 \
    LEXIBEAT_SERVICE_RETAIN=32

WORKDIR /app

# FastAPI, uvicorn and pydantic are the `service` extra — deliberately not `explorer`, which adds
# gradio for a bed-authoring UI this deployment has no use for. The base runtime is numpy, scipy,
# soundfile, pyloudnorm, soxr and pedalboard: no librosa, and so no numba and no llvmlite.
#
# `httpx` is named separately and on purpose: it is not part of the `service` extra, because from
# LexiBeat's side nothing calls out. It is `serve.py` that does — the call home for a voice — so the
# dependency belongs to this image rather than to that package.
# `libatomic1`, and it is not optional. `pedalboard` is what time-stretches an utterance to fit its
# bar, and its native extension links against libatomic — which slim-bookworm does not ship. Without
# it the import fails, the engine falls back to librosa, and the slim runtime deliberately has no
# librosa: the render then dies with `ModuleNotFoundError: No module named 'librosa'`, which names
# the wrong dependency entirely. Nine utterances into a twelve-word loop, having spent the calls.
RUN apt-get update \
    && apt-get install --no-install-recommends -y libatomic1 \
    && rm -rf /var/lib/apt/lists/*

COPY vendor/lexibeat/*.whl /tmp/wheels/
RUN pip install --no-cache-dir /tmp/wheels/lexibeat-*.whl && \
    pip install --no-cache-dir "fastapi>=0.116,<1" "uvicorn>=0.35,<1" "pydantic>=2.9,<3" \
        "httpx>=0.28,<1" && \
    rm -rf /tmp/wheels

# `bundle/` holds ~3.1 GB of content-addressed audio, fetched once with `lexibeat-bundle fetch` and
# never deleted by a reset — the dictionaries arrangement, and for the same reason: it is the owner's
# own data moved between the owner's own machines. `out/` is finished tracks and is disposable.
RUN mkdir -p /var/lib/lexibeat/bundle /var/lib/lexibeat/out \
    && chmod -R a+rwX /var/lib/lexibeat

# `--chmod` on every `COPY`: the installer extracts a release under `umask 077`, so a copied file
# arrives owner-only and root-owned. The container runs as the deploying user and cannot open its
# own entry point — which reads as "Permission denied" from `/bin/sh` with nothing pointing at the
# cause. Nothing runs after these, so changing one rebuilds only the layers from it down.
COPY --chmod=755 deploy/acervo/lexibeat/entrypoint.sh /usr/local/bin/lexibeat-entrypoint
# The entrypoint reads the bundle's root from the pin, so which bundle this image looks for is
# written down once — beside the digest it was fetched against — rather than in three places.
COPY --chmod=755 deploy/acervo/lexibeat/pin.json /app/pin.json
COPY --chmod=755 deploy/acervo/lexibeat/serve.py /app/serve.py

EXPOSE 8000
ENTRYPOINT ["/usr/local/bin/lexibeat-entrypoint"]
# Acervo's own entry point rather than a console script, because the package deliberately refuses to
# serve on its own: a process with no speech backend has nothing to run, and a default one would be
# exactly the provider credential this image refuses to hold.
CMD ["python", "/app/serve.py"]

"""Acervo's side of the retrieval service's translation seam.

The spoken-usage corpus can translate a clip and align it word by word, and it takes both providers
as constructor arguments — `create_app(settings, translation_provider=…, alignment_provider=…)`,
which is a public entry point of that package. So the player's target text is written by **Acervo's
own providers** without the other repository gaining a LiteLLM dependency, a schema-dialect port or
an error-taxonomy mapping: it changes nothing at all.

What lives here is the half that is Acervo's — one structured call, sent home to Acervo's
`POST /companion/text` — and it deliberately imports nothing of that service's. The wiring that knows its prompts, its schemas and
its exception types is `deploy/acervo/speech/serve.py`, in the one image where the package is
installed. That split is what makes this testable from a virtualenv that does not, and must not,
carry FastAPI, uvicorn, yt-dlp and Stanza.
"""

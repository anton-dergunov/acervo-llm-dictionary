"""The one way to draw a sense image: an article in, a brief and a WebP master out.

Two calls, in the order `docs/features/sense-images.md` §03 fixes them: one text call per *lexeme*
that writes a scene brief for every one of its senses at once, then one image call per sense. The
batching is load-bearing rather than an optimisation — a writer that sees both senses of *venom* can
deliberately make them look nothing alike, which is the entire reason per-sense images beat one
image per word.

**This package stands alone**, the same way `acervo.models` does and enforced by the same test. It
imports providers and a chain from `acervo.models` and nothing else of Acervo's: no settings, no
graph, no database, no repository, no wire vocabulary, and not even `acervo.errors` — deciding *what
kind of thing* went wrong is `acervo.models`' job and deciding what Acervo's wire calls it is
`acervo.services.images`', and one import here would collapse that split invisibly.

Standing alone is what lets the request path and the batch sweep share it. `api/` may not import
`acervo.jobs`, so while these five modules lived under `jobs/images/` there was no way to draw a
picture from a route without either breaking that rule or writing the pipeline twice. The style
table, the template and the chain all arrive as parameters, so a caller supplies them from wherever
it legitimately reads them — `Settings` on the server, argv on a laptop, a route on the worker.
"""

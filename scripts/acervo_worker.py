#!/usr/bin/env python3
"""Acervo's own server-side work, in one place.

The Anki sync server is Anki's and the Acervo server answers requests; this is the batch part.
Today that is the Anki robot fed a manifest from outside, the dictionary compiler and a by-hand loop
render. Keeping Anki up to date with the vocabulary is the server's own work, not this. Keeping it one entry point rather than a
service per job is deliberate: these are one-shot commands run through `docker compose run --rm`, so
a new job is a new subcommand and never a new container.

Enrichment is **not** here. A word's clips, pictures and audio are the server's own work, started by
the write that created the word and run by `acervo/work/` — there is no sweep to call.

    acervo_worker.py anki push /input/runs/<id>/manifest.json
    acervo_worker.py dictionary build --id cc-cedict
    acervo_worker.py loop render --owner-email learner@account.example.com --words 12
"""

from __future__ import annotations

import sys

USAGE = "usage: acervo_worker.py {anki|dictionary|loop} ...\n"


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments or arguments[0] in {"-h", "--help"}:
        sys.stderr.write(USAGE)
        return 0 if arguments else 2
    job, rest = arguments[0], arguments[1:]
    if job == "anki":
        from acervo.consumers.anki.cli import main as anki_main

        return anki_main(rest)
    if job == "loop":
        from acervo.loops.cli import main as loop_main

        return loop_main(rest)
    if job == "dictionary":
        from acervo.dictionaries.cli import main as dictionary_main

        return dictionary_main(rest)
    sys.stderr.write(f"unknown job {job!r}\n{USAGE}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

"""Removing a media file, the one way it is done.

A picture, a recording, a track and a story's narration are each megabytes nothing else holds, and
removing one is the only thing the server does to the owner's media that cannot be taken back. It
used to happen at a dozen call sites as a bare `unlink`, leaving no trace: a picture that vanished
could not be told from one that was never drawn.

So every removal goes through here and leaves a line in the activity log saying which file and why.
`reason` is one of four words, so it can be searched for:

- `replaced` — a newer file took its place, and the row now names that one;
- `deleted` — the owner removed the record it belonged to;
- `rollback` — it was written a moment ago for a row that then failed to land, so nothing names it;
- `unclaimed` — a pending photo nobody added.

Writing a file is not recorded here: the row that names it is the record of that, and it replicates.
"""

from __future__ import annotations

from pathlib import Path

from acervo import activity


def remove(media: Path | str, reference: str | None, reason: str) -> bool:
    """Remove `reference` from under `media`. True when a file went.

    A file already gone is not an error and not a line: nothing was removed, and refusing a deletion
    that has in effect happened would help nobody.
    """
    if not reference:
        return False
    path = Path(media).joinpath(reference)
    if not path.is_file():
        return False
    path.unlink(missing_ok=True)
    activity.note("media removed", ref=reference, reason=reason)
    return True

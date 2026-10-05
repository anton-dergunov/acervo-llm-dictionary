"""The one error the API speaks.

Every failure the client is meant to understand carries a code and a message written for the owner.
Anything else is a 500 whose message never reaches the wire.
"""

from __future__ import annotations


class ApiError(Exception):
    """A deliberate refusal, with the status and code the client reads."""

    def __init__(self, status: int, code: str, message: str, waiting_on: str = "",
                 noted: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        # For a refusal that passes with time, a short phrase naming what is being waited for —
        # "Gemini (free tier) is overloaded; Cloudflare Workers AI is out of allowance" — so a job
        # resting on it can say so. Empty when there is nothing more specific than the message.
        self.waiting_on = waiting_on
        # What the activity log should say about this refusal and the owner should not be told:
        # which record was stale and at which revisions, which way a token failed. It never reaches
        # the wire — the message is for a person, and these are for a `grep`.
        self.noted: dict[str, object] = dict(noted or {})


class RecordRefused(Exception):
    """A record that cannot be stored.

    Raised by validation and turned into `400 invalid_record` by the merge, which is what names the
    collection and the id. Kept distinct from `ApiError` so a validation message cannot accidentally
    choose its own status.
    """

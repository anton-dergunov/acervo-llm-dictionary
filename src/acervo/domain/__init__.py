"""The canonical server model and the wire projection.

`SCHEMA_VERSION` lives here rather than in `settings.py` because it is not a setting: no environment
changes it, every client states it on every request, and a mismatch is a 409. Keeping it beside the
environment meant anything that merely *spoke* to the service had to import the service's whole
configuration layer.

`projection.py` is the storage <-> client mapping, `validation.py` the rules every write is held to,
and `ids.py` the three shapes — a record id, an instant, a language tag — that appear in both.
"""

# Bumped when the wire model changes shape. Declared here for the server, in `web/src/api.ts` for the
# interface, and in the scripts that speak this API; a mismatch is a 409 by design.
SCHEMA_VERSION = 19

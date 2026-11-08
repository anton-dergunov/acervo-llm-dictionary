# Take verification: hide the check behind the next take

A new directed loop take is now listened to before it is kept, and recorded once more when it spoke
its direction ([`docs/features/loops.md`](../features/loops.md) §2.4). The check costs about two
seconds on the NAS (Whisper base, CTranslate2 int8,
[`experiments/take-verification/`](../../experiments/take-verification/README.md)), and the generator
asks for one take at a time, so today that is about 2.5 minutes added to a 72-take directed loop.
That is acceptable, and this is what removes it.

## The work

**In LexiBeat, then re-pinned:** `AcervoVoice` keeps two takes in flight instead of one, so the
server checks take N on an idle CPU while the provider records take N+1. A provider call is 2–3.6 s
and a check 2.0 s on the NAS, so the check all but disappears, and the render gets faster on its own
since the provider calls overlap too.

Nothing changes on Acervo's side: the route already serialises checks (one Whisper at a time, four
threads), and two takes of one line never share a key, since `take` is in it.

## How to tell it worked

`acervo-worker loop render --words 12` before and after, on the NAS, and the call log's `check_s=` on
each take line against the provider attempt durations beside it: the check should sit inside the next
take's call.

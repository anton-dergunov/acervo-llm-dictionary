# Take verification: record a loop line again when it spoke its direction

Settled by [`experiments/take-verification/`](../../experiments/take-verification/README.md). A loop's
voice is told how to sound ("Speak a helpful host offering more food, warm and generous…") and now and
then says part of that instead of, or after, its text: «to provide **more**», or «Seek relief from
irritation in the throat» for «cough». The owner cannot record a loop line again, so the server
checks each new take and records it once more when it did that. Nothing else counts as wrong: an
exclamation around the word, a laugh, a shout or a drawn-out word is the emotion the direction asked
for, and the owner wants it kept.

## The rule

Whisper (base, multilingual) transcribes the take, told its language. The text is aligned to the
closest run of the transcript's words; the words outside that run are what was said around the text.
**The take is recorded again when any of those words is a word of the direction it was sent** — three
letters or more, not a stop word, not in the text — or an accent word ("accent", "argentina", …). That
is `sweep.leak` and `check.contained` in the experiment, and it fired on exactly the three takes the
owner judged wrong out of 2,032, with no false alarm, in every model tried.

The direction to compare with is the director note the take route received (`direction` in its
body), plus the accent words — what the experiment measured. Not the whole prompt sent, whose
template words ("read", "line", "aloud") were not measured.

## The work

1. **A pipeline package, `src/acervo/hearing/`**, standing alone like `clips/` and `stories/`: given
   audio bytes, a language, the text and the direction, it returns what was heard and the direction
   words found around the text. faster-whisper (CTranslate2, int8, 4 threads), loaded once per
   process and kept. The alignment and the rule move here from the experiment, with OpenCC folding
   Chinese to simplified characters before comparing. `test_layering.py` gains it.
2. **`services/pronunciations.take()`** calls it after `_speak` and before `take_store.store`, only
   when a direction was sent (no direction, nothing to leak). On a leak it records once more — same
   pair, same key, so the second take replaces the first in the cache — checks that one too, and
   keeps it whatever it says. A cached take is never checked again; it was checked when it was
   recorded. Word pronunciations and story passages are not checked: the owner waits on them, and
   "Record again" is right there.
3. **Observable** (the hard rule in `docs/architecture/observability.md`): the take's `pronounce-take`
   line carries `heard=` and `leaked=` when the rule fired, and `retook=1`; a second leak is
   `result=leaked-twice`, kept and logged. `admin log --failed` must show both — cause one with a stub
   transcriber and look. A check that cannot run (model missing, decode error) logs its sentence and
   lets the take through: the check is never why a loop fails.
4. **The image**: `faster-whisper` and `ctranslate2` in `requirements/server.txt` (PyAV comes with
   them), and the weights baked in from a pinned file, `models/hearing.json` (repo
   `Systran/faster-whisper-base` and a revision), the way `models/encoder.json` is — its `RUN` before
   any `COPY` of Acervo's own files. About 145 MB of weights.
5. **Hide the two seconds** (LexiBeat, then re-pinned): `AcervoVoice` keeps two takes in flight
   instead of one, so the server checks take N on an idle CPU while the provider records take N+1.
   A provider call is 2–3.6 s and a check 2.0 s on the NAS, so the check all but disappears — and the
   render gets faster on its own. Without this step the check adds about 2.5 minutes to a 72-take
   directed loop, which is acceptable, so this step can follow the rest.
6. **Docs**: `docs/features/pronunciation.md` drops speech-to-text from "Not built, deliberately" and
   says where it runs and why only there; `docs/features/loops.md` §2.4 and §2.5 say a take may be
   recorded twice and that the cache holds the checked one.

No schema change and no converter: takes have no table.

## Tests

- The rule, on the experiment's cases as strings: the three leaks fire; «Pfff, bancarse.»,
  «¡Aah! ¡Quejarse!», «Oh, frivolous.», a laugh, «Riley.» for «wryly», and 圖書館 for 图书馆 do not.
- The route with a stub transcriber: a leak records exactly once more and stores the second take; a
  second leak is kept and logged; a cached take is not checked; no direction, no check; a transcriber
  that raises lets the take through and logs.
- One real call, gated with the live tests: faster-whisper base on a stored take, to catch a broken
  image.

# Loops and stories · what is still to do

**Status:** open. The designs as built are [`../features/loops.md`](../features/loops.md) and
[`../features/stories.md`](../features/stories.md). Six pieces, each usable alone. A finished render
stays silent on purpose: the loop or story is in its list when the owner goes back to it.

## 1 · Drawing the favourites

One more order for the make dialogs' draw ([`../features/loops.md`](../features/loops.md) §2.12):
**Favourites**, the starred words first, once words can be starred (§2).

## 2 · Favourites and order

- **A star on words, loops and stories**, with a filter to starred and a "starred first" order. It is
  an owner's mark on a record, so it replicates.
- **Reordering loops and stories** by hand. Both records already carry a `position`; nothing in the
  interface sets it yet.
- **Groups**, only if the lists get long enough that stars and order do not keep them usable.

## 3 · Level

- **A level for loops.** A vocabulary has a level now, and compose, chat and a story's text read it
  ([`../features/standing-rules.md`](../features/standing-rules.md), "The reader"). A loop's sentences
  are written by LexiBeat, so following it there means sending it in `render_request` and a change on
  that side.
- **A level for one story**, overriding the language's, in the story dialog.

## 4 · Listening hands-free

The use is walking with the phone in a pocket: tap once, and loops and stories play.

- **Play a whole story.** Today a part plays its passages in order and stops; leaving the page stops
  it too. A story should play part after part, with the text following along when the screen is
  on.
- **A queue across loops and stories**, with next and previous, as loops already have.
- **One player per device shape**, designed rather than inherited: the phone first, then the
  tablet. On the desktop the now-playing chip leaves the top bar; where it goes instead is part of
  this design.

## 5 · Hearing saved music on its own

The ▶ on a saved piece of music plays the loop it was kept from, voice and all. It should play the
music alone.

- **What exists.** LexiBeat's library already renders a bed with no voice,
  `lexibeat.api.render_music(spec, duration_seconds)`, and a bed replays exactly from its family and
  seed for an engine version. Its HTTP service offers only `POST /loops`, voice and music together.
- **On LexiBeat's side** (the owner's repository, re-pinned in `deploy/acervo/lexibeat/pin.json`): a
  music-only route, `POST /music {family, seed, seconds}`, answering the audio the way a loop's is.
  One route serves this section and the next.
- **On Acervo's side:** keeping a bed queues a `music` job (a new job kind, [`../architecture/jobs.md`](../architecture/jobs.md)),
  which renders about a minute of it, stores the file as media named by its digest, and gives the
  `beds` record an audio reference. That is a change to a replicated record, so `LOCAL_SCHEMA_VERSION`
  goes up and the new column reaches the owner's database through a throwaway converter and
  `./deploy.sh --transition`. The dialog's ▶ plays that file once it is there, and the source loop
  until then.
- Beds kept before this can be given their music by the same job, since family and seed replay them;
  nothing is converted.

## 6 · A sample of each music style

The Music style carousel shows a picture and a sentence; it should also let the owner hear the style.

- One short render per family at a fixed seed, through the same music-only route as §5, made on the
  server when first asked for and kept per engine version, the way loop takes are cached. No record
  and no schema change: it is a cache, emptied by hand.
- A ▶ on the picture in the middle of the carousel plays it, through the players' one
  `registerPlayer` / `silencePlayers` rule. A family LexiBeat adds gets its sample the first time it
  is played.


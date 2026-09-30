# Acervo — UI prototype

Static mock-up of the main window. Open `index.html` directly in a browser; no
server, no build step, no network calls (web fonts aside).

- `index.html` — shell
- `acervo.css` — design language lifted from the Acervo design-document artifact
  (Literata / IBM Plex Sans / IBM Plex Mono, paper-and-teal palette, light and dark)
- `data.js` — fixtures shaped like `web/src/domain.ts`
- `map.js` — the meaning map as a component, reading nothing of `app.js`
- `map-data.js` — a sparse sample of a real map, committed; `map-data.local.js` and `map-local/`
  are the owner's whole map and its pictures, git-ignored and generated (below)
- `app.js` — view logic only; every write, TTS call and capture action is a stub
- `install.html` — the mobile installation gate, with iOS and Android preview links
- `launch.html` — what a cold start shows while the replica is read back from the device
- `img/` — sample generated illustrations, reused from the image benchmark

The floating control in the bottom-right previews phone and tablet widths inside
a desktop browser. It is prototype scaffolding and is not part of the design.
The preview frames count as touch screens: listen buttons stay visible and the
card arrows are hidden, as they would be on a real phone.

It also carries the switches for the article redesign spike:

- **View** — `auto` (Cards in the phone and tablet frames, Page on desktop),
  `page` or `cards`; stands in for a Settings option.
- **▷ Translations** — listen buttons after translations as well.

…and the two for the loops surface:

- **Loops** — opens and closes it.
- **1× / 4× / 12×** — winds the loop's clock on. A word really takes twenty-two
  seconds; at 1× the reveal has its true rhythm, and at 12× a whole loop can be
  watched through in twenty seconds.

There is no audio and there will not be: a fake clock stands in for the track, so
the word being said, the translation arriving and the seek line are all driven by
exactly what drives them in the application. **A translation is never drawn before it has
been spoken** — an unreached word shows a short bar of a fixed width instead — and
the reveal is a pure function of that clock, so dragging backwards puts the answer
away again.

Deep links keep screenshots reproducible: `?open=la obra&frame=phone&view=cards&card=1`,
plus `tr=on`, `theme=dark`, and `size=375x667` to resize the frame.

Stories open the same way: `?story=1&part=0` reads the first written story from its first page
(the last page is the words), `stories=1` alone opens the list, and `reveal=1` turns every
translation over. The first part is drawn as if it were being read aloud: its button lit and its
first sentence tinted, as the application tints the passage that is sounding.

A word can be looked up by tapping it: in a story's text, in a loop's lines in the language being
learned, and in an article's definitions and examples. The tap moves nothing — the story does not
start reading and the loop does not seek — and a sheet at the foot says what the word means in that
sentence. A word you hold is answered from your words, with Open, and Back from its article returns
to the story's page or the loop; any other word waits about a second for a stubbed look-up and offers
Add, which files it in the Inbox. What the tap used to do is the sheet's second button: From here in
a story, Play from this line in a loop. Anything that is not such a word keeps its tap, so a loop's
translation line and a card's edge still seek. Selecting text offers Look up beside Listen, which is
how a phrase is looked up. `tap=<word>` taps the first shown occurrence of a word on the surface a
deep link opened (`?story=1&part=0&tap=migajas`, `?open=picar&tap=nariz`, and a loop with `loop=`
and `t=`), `lookup=slow` answers in three seconds and `lookup=offline` never does. Only words that
also exist in `data.js` open a real article; the story's own words do not.

Photo capture is the Add view's Photo tab, never where Add opens: `?add=photo` is the start, with
nothing switched on. Every photo is shown in one square. `?add=photo&photo=read` is a camera photo,
which *is* that square — "llevada a cabo" tapped, its sentence banded line by line, the sheet below.
`?add=photo&photo=screenshot` is a chosen image taller than the square: it fills the width, scrolls
inside it with a fade at the edge that has more, and is kept as the square on screen. The attestation
photo on `picar` opens the kept square.

For loops: `?loops=1&t=12` is the moment the whole design is for — `picar` is
being said and its translation is still a bar. `t=20` is a few seconds later,
with the answer given and the mark moved to it. `loop=` picks one by id,
`play=1` starts it and `speed=4` winds the clock on.
`la obra` and `animarse` are copied from a real account; `picar` sense 1 has a
deliberately overlong example, to show the one card that has to scroll.
`la sobremesa` is still being filled in on the server: it shows the progress strip, the clip slot
and the closed Cards switch. `fill=searching|none|failed|off` picks how its clip search ends.
`espolvorear` is deliberately the one Spanish word with no `primaryGloss`, so it is the one that
cannot be in a loop — a loop has to choose a single meaning, and nothing fills that in later.
Of the four loops, one has never been rendered and one was made on a server with no sample pack.

The selection: `?select=1` puts eight Spanish words in it, one of
them `espolvorear` so a loop has something to leave out. `sellist=1` opens the bar's list of them,
and `make=loop-selection` or `make=story-selection` opens a dialog from the bar. A word row, a loop
and a story all answer a right-click with a menu and a swipe with their actions. On the map, `Select`
in the peek marks every sense of the word.

## The map

`?map=1` opens the meaning map (`docs/features/meaning-map.md`): one language's senses, laid out by meaning,
with regions named at two levels. It is entered from the rail and, on a phone, from the third
segment of the foot bar, and it follows the language menu. The application draws the `atlas` style;
the other two exist only behind the harness switch.

It draws the owner's real map when `map-data.local.js` exists, and the committed sample (about 85
words per language) otherwise. To generate the real one from an export bundle:

```bash
cd experiments/meaning-space
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python build.py --bundle path/to/acervo-all.zip --pictures
```

`label_model.py` adds the model-written region names; see that directory's README.

On the map the top bar carries the map's own row in place of search, Add and sync: Back, Map, the
counts (not on a phone), Find and its own language switcher. ⌘K leaves the map for search. Each
sense of an article has a button that shows it on the map, for the words the map holds.

Pinch or scroll with two fingers to move; pinch, ⌘ + scroll or a mouse wheel to zoom; double-tap to
zoom in. On a keyboard ⌘= / ⌘− / ⌘0 zoom in, out and fit (Ctrl elsewhere; the browser's page zoom is
suppressed while the map is open), and bare `+ − 0` and the arrows work whenever nothing is being
typed. Tap a word for its peek; tap a region's name to fly to it. Far out the map names its
regions, in the middle its neighbourhoods and their most central words, close in every word with its
sense's emoji, and closest the first gloss under each. Selecting a sense joins it by dashed arcs to
the same word's other senses and by fine lines to its five nearest.

The harness switches are the questions this prototype exists to answer by looking:

- **Style** — `atlas` (land, sea and contours), `constellation` (each sense joined to its nearest,
  as Obsidian's graph is) or `clouds` (a soft tint per region).
- **Labels** — how a region is named: `model` (one call, made once), `words` (the three most
  central headwords) or `terms` (c-TF-IDF over the definitions).
- **Update** — a new layout arriving: the words already there glide to where they now belong and
  the new ones appear with a ring.
- **Sample** — the committed sample, even when the real map is present.

Deep links: `map=1`, `lang=en`, `style=clouds`, `labels=terms`, `focus=cobrar` (peek at a word and
fly to it), `z=4` (zoom from the whole map), `update=1`, `sample=1`, and `mapstate=drawing` or
`mapstate=offline` for the first draw and for a device that has never reached the server. Only the
words that also exist in `data.js` open a real article from the peek; Back then returns to the map
exactly where it was.

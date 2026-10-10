# Pictures

The pictures in the README and on the project's card on the blog. Each is a page of 960×600
rendered at twice that, 1920×1200 (16:10), and each is built from real captures of the application
on a real vocabulary, with a heading and one measured fact beside it.

```
shots.json     what to capture: one entry per shot, as the steps a person would take
shots/         the captures
<name>.html    a picture: captures placed on a page, with its text
style.css      shared by every page; the application's own palette and typefaces
<name>.png     the picture
capture.mjs    takes the shots and renders the pages
```

## Retaking them

```bash
npm install --prefix web           # Playwright, and the fonts the pages use
cp credentials.env.example credentials.env   # once; then fill in the server and the account

node assets/pictures/capture.mjs                 # every shot, then every picture
node assets/pictures/capture.mjs word map        # the named shots, and the pictures of those names
node assets/pictures/capture.mjs --compose       # only render the pages, with no server
```

Needs Google Chrome (Playwright's own Chromium cannot decode the clips' video) and `pngquant`.

- **A shot drives the application as a person does**: the search box, the rail, the gear. It never
  reads the API or the local database, so a change to the data model does not break it. A change to
  the interface can, and `shots.json` is where to follow it: the steps are named in `capture.mjs`.
- **It cannot change the vocabulary.** Every request that is not a read is refused before it leaves
  the browser, except signing in and the routes a shot lists under `allow`. Those are `/chat`,
  `/capture` and `/capture/resolve`, which the server documents as writing nothing, and
  `/photo/read`, which keeps the uploaded test photo pending on the server and creates no record.
  Four shots therefore cost model calls each time they are taken: `chat`, `chat-review`,
  `capture` and `capture-chat` (and `photo` costs one OCR call and one look-up).
- The first run on each screen size pulls the whole vocabulary into a browser profile under
  `output/screenshots/profile/`; later runs start from it. A shot that fails leaves
  `output/screenshots/failed-<name>.png`, which shows where it stopped.
- The words, the story and the loop are named in `shots.json`. When one is deleted from the
  vocabulary, name another there; the text beside it is in the `.html` of the same name.
- `--shots <file> --out <directory>` tries a shot out before it joins the list.
- The answers of `chat` and `capture` come from a model and differ between takes. Read the new
  capture before keeping it, and check that the text on `chat.html` still describes it.
- Before committing, look at every new capture for an account name, an address or a key. Settings ▸
  General and Settings ▸ Providers show them; no shot opens the first, and a shot of the second
  must hide `.model-account`.

- **A shot may be drawn differently from the application where that makes the picture readable**: a
  window narrower or a screen shorter than a real one (`viewport`), a picture drawn smaller or a text
  box taller (`style`). Each `.html` says so in its opening comment. Marks drawn on a capture by the
  page, such as the underlined phrase on `capture.png`, are said there too.

## The pictures

| File | Shows | Captures |
|---|---|---|
| `word.png` | The lead: one word's page in a window over the word list, and the picture of each of its three senses | `word-window`, `word-list`, `word-sense-1..3` |
| `capture.png` | A pasted sentence, the entry drafted from it, and a change asked for in the chat under the draft | `capture-text`, `capture`, `capture-chat` |
| `pictures.png` | Three senses of one word in three styles, with a brief | `pictures-1..3` |
| `clips.png` | An example in an entry that carries a clip, and the player it opens | `clip-example`, `clip` |
| `story.png` | A story part being read, and the story's four pictures | `story-3`, `story-picture-1..4` |
| `loop.png` | A loop playing on a phone, the translation still held back, and the list of loops | `loop`, `loops` |
| `map.png` | The meaning map at one word, and the whole map | `map`, `map-whole` |
| `chat.png` | A question about an entry, and the proposed change under review | `chat`, `chat-review` |
| `photo.png` | A photographed page with a word tapped, and the photo kept on a word | `photo`, `photo-kept` |
| `devices.png` | One word on a phone, a tablet and a desktop | `word-phone`, `word-tablet`, `word` |
| `pipeline.png` | The job a save queues, with one real job's log lines | `activity` |
| `experiments.png` | Six of the experiments: question, measurement, decision | none |

Every number on a picture is from `experiments/README.md` or `docs/ml.md`, and each `.html` says in
its opening comment where its numbers come from. The log lines on `pipeline.png` are one job's lines
from the server's `jobs.log` and `model-calls.log`, shortened by hand; the timings on `photo.png` are
that shot's own lines in the call log.

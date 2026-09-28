# Photo capture · tap a word in what you're reading

**Built**, for languages that put spaces between words, with Google Cloud Vision as the only reader. Every number a
choice below was made by is in [`experiments/photo-capture/`](../../experiments/photo-capture/README.md),
scored against the fixtures in
[`tests/fixtures/photo-capture/`](../../tests/fixtures/photo-capture/README.md). Chinese and Japanese
are a separate spike, not yet run.

A word typed or pasted into Add works for text already on a screen. It is awkward for a word met in
a printed book, and it throws away what a personal dictionary most wants: the sentence the word was
met in, and a memory of where.

## What it does

Add has a **Photo** tab beside Text, Article and YAML. It is never where Add opens, and the camera
turns on only when "Take a photo" is pressed: photo capture is an occasional way in, and a camera
that switches itself on is one nobody asked for. The viewfinder is a square at the top of the screen,
leaving room for a sheet below it, and a second button chooses an existing image or screenshot
instead. Taking the picture freezes the frame, and every recognised word on it becomes tappable.

Tapping a word highlights it, and its sentence in a second colour. The sheet shows that sentence as
editable text with the word marked, and within about a second what the word means **in this
sentence**. From there it is one tap to one of two actions:

- **Add**, for a word the owner does not have. It builds an entry with the sentence as its
  attestation and the photo kept beside it.
- **Open / fold in**, for a word the owner already has. It opens the stored article and offers to
  add this sentence to it.

On a desktop, or a tablet on its stand, it is the same screen with a file picker, paste and drop.

The tapped word is a hint, not the answer. Tapping *new* in "New York" proposes *New York*, and
tapping *echo* in "te echo de menos" proposes *echar de menos*: a model makes that judgement, the
same one resolve makes on typed text.

## Why build it when Lens, Live Text and Google Translate exist

- **iOS Live Text and Google Lens** recognise text on the device, but getting a sentence into Acervo
  is photo → open → select → copy → switch → paste → Add: about eight taps. The sentence is kept only
  if the owner selects all of it, and *which* word is left for capture to guess.
- **Google Translate's camera** needs no taps and translates as you point, and keeps nothing: no
  attestation, no duplicate check, no entry, no picture.

What this has that neither does: about **three taps** (shutter, word, Add); the **sentence kept by
default**, as an attestation; the **duplicate check before any typing**, so a word already held
becomes "add this sentence to it"; the meaning **as used in this sentence**; and the **photo kept as
provenance** — where on the page, or which street sign.

It was built only after passing a kill criterion stated in advance: tap to meaning under about 3 s
at the median on mobile data, and OCR in the centre of the frame no worse than what Live Text copies
from the same photo. Failing either, the fallback was a share target in front of the ordinary
capture flow, letting the platform's own OCR do the reading.

## How it fits what already exists

- **Nothing new writes the graph.** Add is the ordinary `POST /capture` followed by
  `saveArticle(parseArticle(text))`. The sentence goes in as `text`, so it becomes an attestation
  exactly as a pasted one does; the chosen unit goes in as `headword`, a hint resolve may still
  correct. A camera is a transport, and adding a transport must not add a second pipeline.
- **The duplicate path is reused unchanged.** `/capture` already returns `duplicates` and
  `foldable`, and folding a sentence into a held word goes through the article conversation.
- **Geometry comes from an OCR engine, never from a language model.** A multimodal model's boxes are
  approximate and its transcription can be invented, and constrained decoding is not used anywhere
  in Acervo. The model is used only where judgement is needed: which unit was meant and what it means
  here.
- **Online-only, like every write.** It fails visibly when the server cannot be reached and queues
  nothing.

## The pipeline

### 1 · Capture on the device

`PhotoCapture.tsx`: `getUserMedia` with the rear camera, a canvas the frame freezes into so what was
sent is what is on screen, the camera stopped on `visibilitychange`, and plain messages for a denied,
missing or busy camera. The frame is re-encoded through the canvas, which also strips EXIF.

**Every photo is one square, and a camera photo *is* that square.** The shutter keeps exactly the
square the viewfinder showed, taken from the **video frame** — `takePhoto()` was tried first and
dropped, because on the owner's phone its field of view was narrower than the preview's and every
line lost its start and end between framing and reading. So the photo framed, read and kept is one
photo. A square also leaves a phone the height it needs for the sheet, and matches every other
picture in Acervo.

That is not the crop the spike warned against. The spike cut a centre square out of photos framed as
portraits, and so cut off sentences the owner had taken care to include — correct sentences fell from
98% to about 70%. A square viewfinder is framed as a square; nothing is cut that was seen.

**An image that is not square** — a screenshot, a gallery photo — fills the square's width, so a
phone screenshot reads at about its real size, and scrolls up and down inside it with a fade at the
edge that has more. It never scrolls sideways, so a sideways drag along a line is always free to
select a phrase. Vision reads the whole image, so every sentence stays tappable wherever it is
scrolled to; what is **kept** is the square on screen when Add is pressed, cropped on the device and
stored through `POST /photo/store` without a second reading. Do not add a crop the owner did not see.

The upload is at most **2048 px on the long edge at JPEG quality 0.85**, about 400 KB. At 1280 px
Vision still hits the tapped word 98% of the time, but character error on camera sentences rises
from 0.4% to 2.3%, so 1280 is for a poor uplink. A video frame is about 1080–1440 px square.

### 2 · `POST /photo/read`

An image in, a page layout out, with coordinates normalised to the stored image: the detected
language (checked against the owner's vocabularies), words with polygons, confidence and line, lines,
sentences with their word ids and whether the frame cut them off, and the pending `photoRef`.

The server does the cleanup a page needs, so the interface only ever hit-tests:

- **Reading order**, including a two-page spread and a page curving toward the spine.
- **Hyphenation across a line break** (`pala-` / `bra`) joined into one word that keeps both
  polygons, so tapping either half selects it.
- **Sentence segmentation by SaT** (Segment any Text, `sat-3l-sm` through `wtpsplit-lite`), pinned in
  `models/segmenter.json`, baked into the image and loaded when the Photo tab opens. On clean text,
  rules, pySBD and SaT all found every boundary. A photo's text is not clean: it carries a status bar,
  a URL, a heading, show-through from the facing page and a fragment cut by the frame, none of which
  ends in punctuation, so rules and pySBD glued that noise onto the next sentence and were right for
  69% and 74% of taps where SaT was right for 98%. Splitting on Vision's paragraphs first, to spare
  the model, was measured too and loses — Vision starts paragraphs mid-sentence, and SaT falls to 87%.
- **Truncation flagged**, so the sheet can say "this sentence is cut off" rather than store a
  fragment as if it were whole.
- **Low-confidence words kept** and visibly marked. Hiding a blurred word would hide exactly the word
  the owner meant to tap.

### 3 · Tap → meaning, speculatively

Hit-testing is a pure module, `photoText.ts`: the nearest word within a tolerance, then that word's
sentence; dragging across words, or tapping a neighbour, extends the selection into a phrase. **The
tolerance is relative to the line height, not the image**, and a tap near nothing selects nothing, so
the owner sees that the word was not read rather than getting the meaning of the word on the line
above.

Every tap fires **`POST /capture/resolve`** at once — cancelled when the selection moves, cached per
sentence and selection, so tapping back is free. It is `pipeline.understand` — resolve, the
vocabulary checks and the duplicate check — with the tap marked in the text by asterisks, the way the
resolve prompt already reads a pointer, and the prompt's `quick` and `photo` sections switched on. It
returns the resolved unit, a short in-context gloss in `glossLangs[0]`, and `duplicates` and
`foldable`.

**It runs on its own `quick` chain**, the text models in a second order. The owner's `text` chain is
ordered for writing good entries; this call is ordered for answering while a finger is still on the
glass. Gemini 3.5 flash-lite answered in 1.02 s at the median; a stronger Flash was more accurate and
took 4.4 s, which a tap cannot afford.

### 4 · Add

Add is the ordinary `/capture`, carrying the resolution back so compose does not pay for resolve
twice. The server checks every field of it again rather than trusting it, and refuses a sentence its
own text does not contain.

## The photo is kept with the attestation

For a book, the picture shows where on the page the word was. For a sign or a landmark, the picture
*is* the memory. The dictionary is private, so keeping photos of pages raises no question of sharing.

**The model.** An attestation carries `photoRef` — a path relative to `ACERVO_MEDIA_PATH`, as
`imageRef` is for a sense picture — and `photoRegion`, the normalised polygons of the selected words
and their sentence, so the article can draw the same highlight again. `SOURCE_KINDS` includes `sign`,
for text seen out in the world rather than read. **A sign is a photo with no sentence**: an
attestation with empty text is allowed when it carries a photo, and no example is drawn from it.

**Who writes the file, and who writes the row.** A media file and the row naming it must be written by
the same party, or one of them is a lie. Here the server writes the file and the row goes through the
ordinary save, and the rule still holds:

1. `/photo/read` stores the image, EXIF-free and content-addressed, as
   `photos/{owner}/pending/{digest}.jpg`, and returns the ref it will have **once kept**,
   `photos/{owner}/{digest}.jpg`. Nothing ever rewrites a ref, and a second word saved from the same
   photo finds it already kept.
2. The attestation names that ref. `merge_graph` **refuses** a new `photoRef` whose file is neither
   kept nor pending for that owner, and in the same write moves it out of `pending/` — back again if
   the transaction does not commit (`place_photo`, supplied by `services/photo.placer`, so the
   repository never learns where media lives). The row can never name a missing file.
3. A runner tick deletes pending photos older than a day. A photo nobody added costs nothing.
4. The media route serves `photos/{owner}/…` to that owner only, and never a pending one.
5. **A kept photo is not deleted with its attestation**: undo restores the tombstone, and one photo
   may back several words.

**Reading.** A photo is fetched as a blob behind bearer auth and cached in `mediaStore.ts`, as sense
pictures are, so it works offline once seen. The attestation shows a thumbnail — and so does the
example drawn from it, since capture shows a sentence you supplied as that example — and tapping it
opens the full frame with the highlight drawn. The device puts the bytes it uploaded into that cache
under the kept ref before review, so the article being reviewed shows a photo the server does not yet
serve.

**Keeping the photo is a switch** on the sheet, on by default: adding a word without its picture
stays one tap away. **Export leaves photos out**, and the export panel says so.

## Where OCR runs

**Google Cloud Vision (`DOCUMENT_TEXT_DETECTION`) is the reader**, the only row of the `ocr` kind in
`models/catalogue.json`, so a 429 falls through a chain like any other call. It returns word
polygons, block and paragraph structure and a detected language, under the Google project Vertex
already uses. LiteLLM does not cover it, so `models/google_vision.py` reaches it by hand and answers
provider-neutral `OcrWord`s — another engine is one row and one adapter. The first 1,000 images a
month are free, then $1.50 per 1,000.

**RapidOCR on the NAS is not a usable fallback.** It is too slow — 6.7 s at the median for a 2048 px
photo on the NAS's Ryzen, against a 3 s budget from shutter to tappable — and on book photos it hit the
tapped word 68% of the time against Vision's 100%, missing whole blocks where a page tilts. Bigger
local models were slower and no more accurate. On screenshots it matched Vision. Tesseract does poorly
on camera photos, and a multimodal model was rejected as the source of geometry above. So when Vision
is unavailable, the camera says so and the owner tries later.

`src/acervo/ocr/` is a standalone package — layout and segmentation — importing nothing of Acervo's
beyond `acervo.models`; `services/photo.py` is the binding layer, and `test_layering.py` enforces both.

## Interface decisions

- **The highlight is an SVG over the frozen image, in the image's own `viewBox`.** This is not the
  overlay forbidden for the YAML editor: that one failed because two independent text layouts had to
  agree pixel for pixel. Here there is one coordinate system, the image's pixels, and nothing to drift.
- **Frame above, sheet below, never side by side**, for the reason the ask dock is a sheet: it must
  work on a tablet in portrait.
- **The sentence box is editable** before Add, so an OCR error is fixed in the text that is stored
  rather than preserved in it.

## Not built

An image share target is one of the capture transports
([`../plans/capture-transports.md`](../plans/capture-transports.md), A2); Chinese and Japanese are
[`../plans/languages/chinese.md`](../plans/languages/chinese.md); a photo sentence folded into a held
word losing its photo is [`../plans/issues.md`](../plans/issues.md) §4.

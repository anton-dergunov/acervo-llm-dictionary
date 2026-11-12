# Pictures whose strokes are the character

**Status: round 1 judged 12 Nov 2026. The idea works; the prompts needed tightening. Round 2 is
prepared and ready to draw.** The plan this serves is
[`docs/plans/languages/character-pictures.md`](../../docs/plans/languages/character-pictures.md);
it stays there until the owner decides.

## Question

Some characters began as drawings: 人 a person, 山 three peaks, 木 a tree. Can an image model draw
what such a character depicted **so that the character's strokes are the object's parts**?
- 人's two strokes are the person's body and legs.
- 大's horizontal stroke is the arms held wide.
- 木's strokes are the branches, the trunk and the roots.

A picture like that ties the shape to the meaning. A picture with the character laid over it does not.

That is the failure to design against. Asked plainly ("show some hanzi as a picture and how they
overlay onto something that matches their meaning"), a capable chat image model pasted the character
onto a scene: a tea cup with 茶 printed on it, a book with 书 on its pages. That is of no use to a
learner. Told exactly which stroke is which part ("the strokes are the person's legs; for 大 the top
stroke is the arms held wide open"), it drew 人 and 大 correctly. The other characters, which got no
such guidance, stayed pasted on.

So the experiment does not test a naive prompt. It gives every model the guidance that worked, for
every character, from the start: **a stroke script**.

## Method

**Characters** (`run.py` `CHARACTERS`). Each must be `pictographic` or `ideographic` in Make Me a
Hanzi's own etymology (`dictionary.txt`, pinned in [`pin.json`](pin.json)). **The source decides,
not a model**: `prepare` drops any character the source disagrees with. Each round's
`results/round-N/characters.json` holds each character's type and hint as the source gives them.
- **Round 1**, 22 characters whose modern form still looks like the object, including compounds of
  the simple ones (林 森 明 休 从):

  > 人 大 从 休 山 水 木 林 森 口 日 月 明 火 雨 田 门 竹 井 册 羊 凸

  - From the plan's first list, 鱼 马 鸟 are left out because simplification erased the drawing, and
    目 because the eye was turned upright.
  - 刀 has no etymology in the source and was replaced by 凸.
- **Round 2**, the five that round 1 left without a correct picture (木 林 森 月 明), then twenty new
  ones, again with compounds and the pair 凸/凹:

  > 子 女 耳 手 心 弓 伞 网 禾 米 爪 舟 立 川 旦 本 果 众 炎 凹

**The stroke script** ([`scripts.yaml`](scripts.yaml)), one per character, written by hand from the
source's hint and the character's oldest forms:
- `object`: what the character depicted.
- `strokes`: one entry per stroke, in the pinned stroke order, each saying **where the stroke lies**
  and **which part of the object it becomes**. `prepare` refuses a script whose count differs from
  the character's.
- `history`: how the modern form drifted from the drawing.
- `layout`: how the object fills the square the way the character fills its box.
- `exact` (since round 2): the details of the shape a picture must keep. These are which strokes touch,
  cross or stand apart, and which end in a hook or a plain point. They are read from the pinned outlines,
  because round 1's pictures most often broke exactly these.

The stroke positions are written by hand. An earlier version described them automatically from the
stroke data's medians, and a brush stroke's entry read as a turn ("down to the right to the top
centre, then turning…").

**Two ways of asking**, both carrying the same script and the same art direction:
- **`text`**: the prompt alone ([`prompts/text.md`](prompts/text.md)).
- **`edit`**: the character's strokes, rendered from the pinned stroke data **in black on white**, are
  sent as the picture to draw over ([`prompts/edit.md`](prompts/edit.md)).

The strokes are listed in stroke order and never numbered.

**The art direction** ([`prompts/direction.md`](prompts/direction.md)):
- The strokes are bold, solid black brush strokes of regular script, in their places and shapes, so
  the ink alone still reads as the character.
- Every stroke is kept as written. None is added, dropped, merged, hooked, or turned into a flame,
  drop or branch. Strokes that touch in the character touch in the picture.
- The object is drawn over and around the strokes, not beside them.
- **Bold solid black belongs to the strokes alone.** Everything else is lighter but clearly visible.
  Thin outlines and greys are welcome, but no other thick black mark that could be taken for a stroke.
- There is no text, no number, no stroke-order mark, no frame and no backdrop.

`prepare` writes every filled prompt to `out/round-N/prompts/` before anything is spent.

**Models** (`run.py` `MODELS`):

| Id | Model | Takes | Rounds |
| --- | --- | --- | --- |
| `nano-banana-2` | Vertex `gemini-3.1-flash-image` | 2 per way | 1, 2 |
| `nano-banana-pro` | Vertex `gemini-3-pro-image` | 2 per way | 1, 2 |
| `flux-2-klein` | Cloudflare `@cf/black-forest-labs/flux-2-klein-4b` | 1 per way | 1 only, on 人 山 木 日 月 口 田 林 |

- Klein drew only a sample, because of Cloudflare's free allowance. It was dropped after round 1.
  Klein now accepts reference pictures, since this experiment: FLUX.2 klein takes up to four, each
  under 512 px a side, and the Cloudflare adapter sends them (`src/acervo/models/cloudflare.py`).
- Models are not ranked against each other; each is asked at its family's own settings.
- 2.5 Flash Image and Flash-lite are left out. A feature would draw each character once, so the
  stronger model is the one worth knowing about.

Round 1 drew 192 pictures for $17.69. Round 2 is 200 pictures, about $20.

**Judging** (`review.py`). The owner judges on the tablet, **blind**. Each character's pictures are
shuffled into letters, with the key kept in `out/round-N/key.json`. Each page shows one character,
with all its pictures side by side so they can be compared:

- **A score from 1 to 5** under each picture: how much the owner likes it, all things considered.
  A score of 1 is a rejection.
- **★ one best picture** per character. A full ranking of 8–10 pictures would be slow, and the order
  among the weaker ones would mostly be noise; the star settles the top.
- **Two questions** per picture, in a table below the grid, each answered *yes / partly / no*:
  1. **Strokes**: do its parts lie where the character's strokes are, so that it still reads as the
     character?
  2. **Depicts**: does it show what the character depicted?

  Round 1 also asked **Remember** ("would it help you remember the character?"). It was too
  subjective to answer apart from the score, so it is dropped.

Tapping a picture opens it full screen, with arrows to step through the character's other pictures.
An "Overlay strokes" switch lays the character's exact strokes over every picture, each in its own
colour. The colours are for the judge only; the models never see them.

## Running it

On the laptop, from the repository root:

```bash
uv pip install -r experiments/character-pictures/requirements.txt   # resvg-py, for the strokes
python3 deploy/acervo/strokes/fetch.py                               # the pinned stroke data
.venv/bin/python experiments/character-pictures/run.py fetch         # dictionary.txt, verified
.venv/bin/python experiments/character-pictures/run.py prepare       # strokes, prompts, characters.json
```

**The draw takes about two hours.** Allow about a minute a picture, and longer when Vertex is busy.
In round 1, about one call in two was rate-limited and rested. The two models run at once, one call
each at a time:

```bash
caffeinate -i .venv/bin/python experiments/character-pictures/run.py draw 2>&1 \
  | tee -a experiments/character-pictures/out/round-2/draw.log
```

- **Watch it**: `tail -f experiments/character-pictures/out/round-2/draw.log`. There is one line per
  picture, and one per rest when a provider is busy.
- **Resume**: run the same command again. A picture already on disk is never drawn twice, so a stop,
  a crash or a closed lid costs only the call in flight.
- **It stops on its own** when a provider refuses for a reason that is not about one picture: a key,
  a model id, an expired login, or a dropped reference picture. It says why, as a `STOPPED:` line at the end.
- **If Vertex says the Google login has expired**, run `gcp-personal` (or `gcloud auth
  application-default login`), then rerun.
- **To draw a single model**: `--models nano-banana-pro`. **Only some characters**: `--characters 木林森`.
  Every call is logged to `out/round-2/draws.jsonl` with its time and cost.

**Judging**, from the tablet over Tailscale. It can start before the draw has finished; reload the page
to see new pictures:

```bash
.venv/bin/python experiments/character-pictures/review.py --host "$(tailscale ip -4)"
```

**Afterwards**, `run.py report` unblinds the labels and writes the round's `results/round-N/`:
- `report.md` and `summary.json`: for each model and way, the share answering yes / partly / no on
  each question, the mean score, the shares scored 4–5 and 1, and how often it drew the starred
  picture. Per character: the starred picture, the combinations that got yes on both questions, and the
  top score.
- `labels.json`, `key.json` and `draws.jsonl`.

Then write up the result here and put the decision in the plan.

Round 1 was drawn and judged with `run.py` and the prompts as they stood at commit `8bdb68f`. Those
prompts had numbered strokes and a coloured reference. Its pictures are kept, ignored, in
`out/round-1/`.

## Licences

- **Stroke data**: Make Me a Hanzi's strokes as packaged by `hanzi-writer-data@2.0.1`, under the
  Arphic Public License (`deploy/acervo/strokes/pin.json`).
- **Etymology**: Make Me a Hanzi's `dictionary.txt`, under the GNU LGPL v3 or later (its `COPYING`).
  It is fetched pinned into `out/cache/` and never committed. `results/round-N/characters.json` quotes
  the hints for that round's characters, with attribution.
- **Pictures**: they are media, regenerable, and stay in the ignored `out/`.

## Results

### Round 1 (12 Nov 2026)

[`results/round-1/report.md`](results/round-1/report.md) has the full report. The owner's notes are in
[`results/round-1/notes.md`](results/round-1/notes.md): the failures they saw, per character and in
general, edited from what they dictated while judging.

All 192 pictures were judged:

| Model | Way | n | Mean score | Scored 4–5 | Scored 5 | Scored 1 | Strokes yes | ★ best |
| --- | --- | --: | --: | --: | --: | --: | --: | --: |
| Nano Banana 2 | text | 44 | 3.59 | 59% | 36% | 14% | 48% | 9 |
| Nano Banana 2 | edit | 44 | 3.66 | 59% | 34% | 9% | 41% | 4 |
| Nano Banana Pro | text | 44 | 3.70 | 57% | 45% | 11% | 57% | 2 |
| Nano Banana Pro | edit | 44 | 3.50 | 59% | 25% | 14% | 41% | 3 |
| klein | text | 8 | 1.00 | 0% | 0% | 100% | 12% | 0 |
| klein | edit | 8 | 3.00 | 38% | 12% | 12% | 25% | 0 |

- **The idea works.** 18 of 22 characters got a starred picture. The owner chose to continue.
  - 木, 林, 森 and 明 had no correct one.
  - 月 got its star only after a check.
- **Nano Banana 2 and Pro are level** on the scores: means 3.62 and 3.60, with 58–59% of pictures scored 4–5.
  - Nano Banana 2 drew 13 of the 18 starred pictures, at half the price ($0.067 against $0.134 a picture).
  - Pro asked by text had the most 5s (45%).
  - Both are kept for round 2, to choose between them before a full run.
- **Klein is dropped.** It averaged 2.0, and 9 of its 16 pictures were rejected (scored 1). On klein's
  own 8 characters and first takes, Nano Banana 2 averaged 4.0 and Pro 3.8.
- **Neither way of asking wins.** Text pictures were starred 11 times and edit pictures 7 times, and
  each way's typical failure came from its prompt:
  - **Stroke-order numbers** appeared only in text-way pictures, whose prompt listed "Stroke 1, …".
  - **Coloured ink** appeared mostly in edit-way pictures, whose reference had each stroke in its own colour.

  Round 2 removes both causes: no numbers, a black reference.
- **The other failures:**
  - **A changed character.** A stroke was replaced by a flame, a raindrop or a branch; strokes were added
    or dropped; strokes were re-styled into curls.
  - **A hook on 木's trunk**, in 木, 林 and 森.
  - **Inner lines floating free** of the stroke they should join, in 月 and 明.
  - **Black parts of the drawing read as strokes**: shoes, roots, a mouth, a dark cloud.
  - **The object drawn beside the strokes** rather than on them.
  - **Frames and backdrops.**

  Each is now a rule in the art direction or a line in a script's `exact`.
- **"Strokes yes" is an upper bound.** It was answered at a glance. Checked against the pinned
  strokes, 月 H and 明 C and D were wrong although marked yes: their inner lines float free of the
  left stroke. A detached or hooked stroke is easy to miss on a tablet.

**Answers to questions raised while judging:**
- **木's hook.** It is not the form taught here. The pinned stroke data writes the trunk as a plain
  vertical ending in a point, as the mainland standard does. The hooked trunk is a calligraphic and
  handwriting variant, which is why the models draw it. 林's and 森's trees have no hook either.
- **Handwritten or printed?** They are the same character in two typefaces.
  - The stroke data is Arphic's Kaiti, brush-written regular script (楷书). The app's text is set in a
    printed typeface, with squarer, evenly thick strokes.
  - The pictures should follow the regular-script form, since they show strokes as they are written,
    and the Write sheet teaches the same data. A print-like picture is acceptable when its strokes are
    the same and join in the same places.
  - The forms differ in one detail met here: in print, 月's inner lines touch both sides; in regular
    script they touch the left and stop short of the right.
- **Must 月's and 明's inner lines touch?** They must touch the left stroke. The right may touch or
  leave a small gap.

### Round 2

What changed, from round 1's failures:
- The reference picture is black.
- The strokes are not numbered.
- Bold black is kept for the strokes, without forbidding thin dark lines and greys, so pictures do not wash out.
- Every stroke is kept as written.
- Each script lists its `exact` joins and ends.
- Klein is dropped, and Remember is no longer asked.

Not yet drawn.

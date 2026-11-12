# Pictures whose strokes are the character

**Status: built 12 Nov 2026; drawn overnight, judging next.** The plan this serves is
[`docs/plans/languages/character-pictures.md`](../../docs/plans/languages/character-pictures.md);
it stays there until the owner decides.

## Question

Some characters began as drawings: 人 a person, 山 three peaks, 木 a tree. Can an image model draw
what such a character depicted **so that the character's strokes are the object's parts**? 人's two
strokes are the person's body and legs; 大's horizontal stroke is the arms held wide; 木's are the
branches, the trunk and the roots. A picture like that ties the shape to the meaning. A picture
with the character laid over it does not.

That is the failure to design against. Asked plainly ("show some hanzi as a picture and how they
overlay onto something that matches their meaning"), a capable chat image model drew a tea cup with
茶 printed on it and a book with 书 on its pages: the character pasted onto a scene, of no use to a
learner. Told exactly which stroke is which part ("the strokes are the person's legs; for 大 the top
stroke is the arms held wide open"), it drew 人 and 大 correctly. The other characters, which got no
such guidance, stayed pasted on.

So the experiment does not test a naive prompt. It gives every model the guidance that worked, for
every character, from the start: **a stroke script**.

## Method

**Characters** (`run.py` `CHARACTERS`). There are 22, chosen because the modern form still looks like
the object:

> 人 大 从 休 山 水 木 林 森 口 日 月 明 火 雨 田 门 竹 井 册 羊 凸

- They include compounds of the simple ones (林 森 明 休 从), to see whether composition survives.
- From the plan's first list, 鱼 马 鸟 are left out because simplification erased the drawing, and 目
  because the eye was turned upright.
- **The source decides, not a model.** Each character must be `pictographic` or `ideographic` in
  Make Me a Hanzi's own etymology (`dictionary.txt`, pinned in [`pin.json`](pin.json)). `prepare`
  drops any the source disagrees with. 刀 has no etymology there and was replaced by 凸 ("a
  rectangle with a bulge").
- [`results/characters.json`](results/characters.json) holds each character's type and hint as the
  source gives them.

**The stroke script** ([`scripts.yaml`](scripts.yaml)), one per character, written by hand from the
source's hint and the character's oldest forms:
- `object`: what the character depicted.
- `strokes`: one entry per stroke, in the pinned stroke order, each saying **where the stroke lies**
  and **which part of the object it becomes**. `prepare` refuses a script whose count differs from
  the character's.
- `history`: how the modern form drifted from the drawing.
- `layout`: how the object fills the square the way the character fills its box.

An earlier version described each stroke's position automatically from the stroke data's medians.
A brush stroke's entry read as a turn ("down to the right to the top centre, then turning…"), so
the positions are written by hand.

**Two ways of asking**, both carrying the same script and the same art direction:
- **`text`**: the prompt alone ([`prompts/text.md`](prompts/text.md)).
- **`edit`**: the character's strokes, rendered from the pinned stroke data with **each stroke in its
  own colour**, are sent as the picture to draw over ([`prompts/edit.md`](prompts/edit.md)). The
  prompt names each stroke by its number and colour. A black glyph would not tell the model which
  stroke is which; the colours do.

**The art direction** ([`prompts/direction.md`](prompts/direction.md)):
- The parts that are strokes are drawn in **bold black brush ink**, in the stroke's place and shape,
  so the ink alone still reads as the character.
- Everything else is **pale watercolour**, so it never looks like an extra stroke.
- Writing the character, or any text, anywhere in the picture is forbidden.

`prepare` writes every filled prompt to `out/prompts/` before anything is spent.

**Models** (`run.py` `MODELS`):

| Id | Model | Takes | Characters |
| --- | --- | --- | --- |
| `nano-banana-2` | Vertex `gemini-3.1-flash-image` | 2 per way | all 22 |
| `nano-banana-pro` | Vertex `gemini-3-pro-image` | 2 per way | all 22 |
| `flux-2-klein` | Cloudflare `@cf/black-forest-labs/flux-2-klein-4b` | 1 per way | 人 山 木 日 月 口 田 林 |

- Klein draws only a sample. Cloudflare's free allowance is about 95 pictures a day at 1024 px, and an
  input picture costs more.
- Klein takes reference pictures since this experiment. FLUX.2 klein accepts up to four, each under
  512 px a side, and the Cloudflare adapter now sends them (`src/acervo/models/cloudflare.py`).
- Models are not ranked against each other; each is asked at its family's own settings.
- 2.5 Flash Image and Flash-lite are left out. A feature would draw each character once, so the
  stronger model is the one worth knowing about.

That makes 192 pictures, about $18 on Vertex.

**Judging** (`review.py`). The owner judges on the tablet, **blind**. Each character's pictures are
shuffled into letters, with the key kept in `out/key.json`. Each page shows one character, with all
its pictures side by side so they can be compared:

- **A score from 1 to 5** under each picture: how much the owner likes it, all things considered.
  Some pictures are much prettier than others, and the questions below do not capture that.
- **★ one best picture** per character. A full ranking of 8–10 pictures would be slow, and the order
  among the weaker ones would mostly be noise; the star settles the top, where preference matters.
- **Three questions** per picture, in a table below the grid, each answered *yes / partly / no*:
  1. **Strokes**: do its parts lie where the character's strokes are, so that it still reads as the
     character?
  2. **Depicts**: does it show what the character depicted?
  3. **Remember**: would it help you remember the character, by linking its strokes to that meaning?

Tapping a picture opens it full screen, with arrows to step through the character's other pictures
at that size.

An "Overlay strokes" switch lays the character's exact strokes over every picture. That answers
question 1 at a glance, and it previews a cheap option for a feature: drawing the exact strokes over
a picture that already lines up with them.

## Running it

On the laptop, from the repository root:

```bash
uv pip install -r experiments/character-pictures/requirements.txt   # resvg-py, for the strokes
python3 deploy/acervo/strokes/fetch.py                               # the pinned stroke data
.venv/bin/python experiments/character-pictures/run.py fetch         # dictionary.txt, verified
.venv/bin/python experiments/character-pictures/run.py prepare       # strokes, prompts, characters.json
```

**The draw runs overnight.** Allow about a minute a picture, and longer when the providers rest it.
The three models run at once, one call each at a time:

```bash
caffeinate -i .venv/bin/python experiments/character-pictures/run.py draw 2>&1 \
  | tee -a experiments/character-pictures/out/draw.log
```

- **Watch it**: `tail -f experiments/character-pictures/out/draw.log`. There is one line per picture,
  and one per rest when a provider is busy.
- **Resume**: run the same command again. A picture already on disk is never drawn twice, so a stop,
  a crash or a closed lid costs only the call in flight.
- **It stops on its own** when a provider refuses for a reason that is not about one picture: a key,
  a model id, an expired login, or a dropped reference picture, since the editing way would then not
  be tested. It says why, as a `STOPPED:` line at the end.
- **If Vertex says the Google login has expired**, run `gcp-personal` (or `gcloud auth
  application-default login`), then rerun.
- **To draw a single model**: `--models nano-banana-pro`. Every call is logged to `out/draws.jsonl`
  with its time and cost.

**Judging**, from the tablet over Tailscale. It can start before the draw has finished; reload the page
to see new pictures:

```bash
.venv/bin/python experiments/character-pictures/review.py --host "$(tailscale ip -4)"
```

**Afterwards**, `run.py report` unblinds the labels and writes the files below to `results/`. Then
write up the result here and put the decision in the plan.
- `report.md` and `summary.json`: for each model and way, the share answering yes / partly / no on
  each question and on all three, the mean score, and how often it drew the starred picture; per
  character, the starred picture, the combinations that got yes on all three, and the top score.
- `labels.json`, `key.json` and `draws.jsonl`.

## Licences

- **Stroke data**: Make Me a Hanzi's strokes as packaged by `hanzi-writer-data@2.0.1`, under the
  Arphic Public License (`deploy/acervo/strokes/pin.json`).
- **Etymology**: Make Me a Hanzi's `dictionary.txt`, under the GNU LGPL v3 or later (its `COPYING`).
  It is fetched pinned into `out/cache/` and never committed. `results/characters.json` quotes the
  hints for the 22 characters, with attribution.
- **Pictures**: they are media, regenerable, and stay in the ignored `out/`.

## Results

Not yet judged.

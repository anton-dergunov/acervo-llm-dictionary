# Pictures whose strokes are the character

**Status: round 2 judged 13 Nov 2026. Nano Banana 2 drawing over the character's strokes is the
way forward. Round 3 (月 again and thirty new characters, that model and way only) is prepared and
ready to draw.** The plan this serves is
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

- **Round 3**, 月 again, then thirty new ones: sixteen pictographs and fourteen ideographs. The
  ideographs include the pairs 上/下 and 末/未; 末 and 未 differ only in which line across is longer.

  > 牛 贝 衣 自 角 瓜 云 户 犬 羽 车 巾 穴 豆 兔 龟 · 上 下 天 尖 男 好 采 看 苗 灭 坐 末 未 岩

  - 舌, 戈, 又, 矢 and 丘 were considered and left out, because their strokes do not map cleanly onto
    the parts of one picture.

**The stroke script** ([`scripts.yaml`](scripts.yaml)), one per character, written by hand from the
source's hint and the character's oldest forms:
- `object`: what the character depicted.
- `strokes`: one entry per stroke, in the pinned stroke order, each saying **where the stroke lies**
  and **which part of the object it becomes**. `prepare` refuses a script whose count differs from
  the character's.
- `history`: how the modern form drifted from the drawing.
- `layout`: how the object fills the square the way the character fills its box.
- `exact` (since round 2): the details of the shape a picture must keep. These are which strokes touch,
  cross or stand apart, which end in a hook or a plain point, and which lengths and sizes tell the
  character apart. They are read from the pinned outlines, because round 1's pictures most often broke
  exactly these. Since round 3, touches and crossings are measured, not judged by eye: each stroke is
  rendered on its own and compared with the others.

The stroke positions are written by hand. An earlier version described them automatically from the
stroke data's medians, and a brush stroke's entry read as a turn ("down to the right to the top
centre, then turning…").

**The way of asking: `edit`.** The character's strokes, rendered from the pinned stroke data **in solid
black on white**, are sent as the picture to draw over. The whole script goes with them as the
prompt ([`prompts/edit.md`](prompts/edit.md)). So the reference picture and the text description
always travel together.
- Rounds 1 and 2 also asked **by text alone**, the same prompt without the picture. Round 2 settled
  it: text broke the strokes in 8 of 25 characters, editing in 2.
- The strokes are listed in stroke order and never numbered.

**The art direction** ([`prompts/direction.md`](prompts/direction.md)):
- The strokes are bold, solid black brush strokes of regular script, in their places and shapes, so
  the ink alone still reads as the character.
- Every stroke is kept as written, whole and at its full length. None is added, dropped, merged,
  hooked, or turned into a flame, drop or branch. Strokes that touch in the character touch in the
  picture.
- Each stroke keeps its direction, and each part of the character keeps its size and place. The
  character is never widened, narrowed or moved off the reference.
- **The strokes stay plain written strokes** (since round 3). Nothing grows out of them, and no bark
  or texture is painted on them. The object lies behind and around them, each part on its own stroke.
- **The strokes are on top.** Nothing covers a stroke beyond its edge. Ground stays below the lowest
  stroke.
- **Bold solid black belongs to the strokes alone.** Everything else is lighter but clearly visible.
  Thin outlines and greys are welcome, but no other thick black mark or dark shape that could be taken
  for a stroke, and no stray dot.
- The character appears once. There is no text, no number, no stroke-order mark, no frame and no
  backdrop.
- A person has a face and clothes.

`prepare` writes every filled prompt to `out/round-N/prompts/` before anything is spent.

**Models** (`run.py` `MODELS`):

| Id | Model | Takes | Rounds |
| --- | --- | --- | --- |
| `nano-banana-2` | Vertex `gemini-3.1-flash-image` | 2 per way; 8, edit only, in round 3 | 1, 2, 3 |
| `nano-banana-pro` | Vertex `gemini-3-pro-image` | 2 per way | 1, 2 |
| `flux-2-klein` | Cloudflare `@cf/black-forest-labs/flux-2-klein-4b` | 1 per way | 1 only, on 人 山 木 日 月 口 田 林 |

- Pro was dropped after round 2. Drawing over the strokes, it scored 3.28 on average against Nano
  Banana 2's 3.71 and drew 6 starred pictures to its 11, at twice the price.
- Klein drew only a sample, because of Cloudflare's free allowance. It was dropped after round 1.
  Klein now accepts reference pictures, since this experiment: FLUX.2 klein takes up to four, each
  under 512 px a side, and the Cloudflare adapter sends them (`src/acervo/models/cloudflare.py`).
- Models are not ranked against each other; each is asked at its family's own settings.
- 2.5 Flash Image and Flash-lite are left out. A feature would draw each character once, so the
  stronger model is the one worth knowing about.

Round 1 drew 192 pictures for $17.69, and round 2 199 for $20.03. Round 3 is 248 pictures, about $17.

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

- **↻ Redraw later** (since round 3) marks a character that is not good enough yet, keeping its
  star. The owner will go over every character once all are drawn, and redraw the marked ones.
  `report` lists them.

Tapping a picture opens it full screen, with arrows to step through the character's other pictures.
An "Overlay strokes" switch lays the character's exact strokes over every picture, each in its own
colour. The colours are for the judge only; the models never see them.

## Rules for later rounds

What rounds 1–3 taught, for whoever writes the next scripts or prompts. The prompts and `run.py`
already enforce the parts marked *(enforced)*.

**The reference picture sent to the model** is the character's strokes in **solid black on white,
and nothing else**: no colour, no numbers, no labels, no grid. *(enforced: `prepare` and `draw` refuse
a reference with any colour in it.)*
- Round 1's coloured reference came back as coloured ink. Its numbered strokes came back as
  stroke-order numbers drawn into the pictures.
- A session may draw coloured, numbered sheets to work out a script, but only in its scratchpad. They
  are never sent to a model.

**The prompt**:
- Never number the strokes.
- Never ask for text.
- Always send the reference picture and the script together. Text alone breaks the strokes.

**A stroke script** (`scripts.yaml`):
- **`object`** comes from the source's hint and the oldest forms, never a fresh mnemonic.
  - Where the owner has a picture in mind, the script follows it: 月 waxes on the right.
  - Name a direction whenever one matters: which way a person faces, which way a crescent curves.
- **`strokes`**: one line per stroke, in the pinned order.
  - Each line says where the stroke lies as the viewer sees it, and which part it becomes.
  - Choose characters whose strokes map onto the parts of one picture. Leave out those that do not.
- **`exact`** is read from the outlines, never from memory.
  - Measure touches and crossings by rendering each stroke alone.
  - Name the hooks and plain ends (木's trunk has no hook).
  - Name the lengths that tell the character apart (末/未).
  - Name the sizes of a compound's parts (林's taller right tree).
- **`layout`**:
  - Put the object behind the strokes, each part on its own stroke.
  - Keep ground and water below the lowest stroke.
  - Keep colours pale, and never dark next to a stroke.
  - People always have a face (eyes, nose, mouth) and simple clothes.
  - Never ask for a stroke to become a flame, drop, branch or root tip.

**Judging**:
- The strokes decide the score; check them against the overlay before starring.
- A detached, hooked or straightened stroke is easy to miss at a glance.

## Running it

On the laptop, from the repository root:

```bash
uv pip install -r experiments/character-pictures/requirements.txt   # resvg-py, for the strokes
python3 deploy/acervo/strokes/fetch.py                               # the pinned stroke data
.venv/bin/python experiments/character-pictures/run.py fetch         # dictionary.txt, verified
.venv/bin/python experiments/character-pictures/run.py prepare       # strokes, prompts, characters.json
```

**The draw takes about three and a half hours.** Vertex lets Nano Banana 2 draw about one picture a
minute, with short bursts of up to four. That held on two projects: 1.07 a minute over round 2, 1.29
early in round 3.
- So `draw` starts one call every 50 s (the model's `pace` in `run.py`, or `--pace` for one run),
  instead of calling as fast as answers come.
- Unpaced, about one call in two was refused with a 429.
- A 429 that still comes rests 60 s, then longer.

Run it in your own terminal:

```bash
caffeinate -i .venv/bin/python experiments/character-pictures/run.py draw 2>&1 \
  | tee -a experiments/character-pictures/out/round-3/draw.log
```

- **Watch it**: `tail -f experiments/character-pictures/out/round-3/draw.log`. There is one line per
  picture, and one per rest when a provider is busy.
- **A picture refused**: once in round 2, the model answered with a sentence instead of an image.
  The last line then says how many pictures are missing; run the same command again for them.
- **Resume**: run the same command again. A picture already on disk is never drawn twice, so a stop,
  a crash or a closed lid costs only the call in flight.
- **It stops on its own** when a provider refuses for a reason that is not about one picture: a key,
  a model id, an expired login, or a dropped reference picture. It says why, as a `STOPPED:` line at the end.
- **If Vertex says the Google login has expired**, run `gcp-digest` (or `gcloud auth
  application-default login`), then rerun.
- **Only some characters**: `--characters 月牛`. **Fewer takes**: `--limit 4`. **Another pace**:
  `--pace 40`; a log full of `rate_limited` lines means the pace is too fast.
  Every call is logged to `out/round-3/draws.jsonl` with its time and cost.

**Judging**, from the tablet over Tailscale. It can start before the draw has finished; reload the page
to see new pictures:

```bash
.venv/bin/python experiments/character-pictures/review.py --host "$(tailscale ip -4)"
```

**Afterwards**, `run.py report` unblinds the labels and writes the round's `results/round-N/`:
- `report.md` and `summary.json`: for each model and way, the share answering yes / partly / no on
  each question, the mean score, the shares scored 4–5 and 1, and how often it drew the starred
  picture. How the score and the star go with each answer to *strokes* and *depicts*. Per character:
  the starred picture, the combinations that got yes on both questions, and the top score. The
  characters marked to redraw.
- `labels.json`, `key.json` and `draws.jsonl`.

Then write up the result here and put the decision in the plan.

Each round was drawn and judged with `run.py` and the prompts as they stood at one commit:
- round 1 at `8bdb68f`, with numbered strokes and a coloured reference;
- round 2 at `cffc334`, by text and by editing, with both models.

Their pictures are kept, ignored, in `out/round-N/`.

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

### Round 2 (13 Nov 2026)

[`results/round-2/report.md`](results/round-2/report.md) has the full report. The owner's notes, with
every letter unblinded, are in [`results/round-2/notes.md`](results/round-2/notes.md).

199 of 200 pictures were drawn and judged. The missing one, 林 by Nano Banana 2 editing, came back as
a sentence instead of an image.

| Model | Way | n | Mean score | Scored 4–5 | Scored 1 | Strokes yes / no | Depicts yes | ★ best |
| --- | --- | --: | --: | --: | --: | --: | --: | --: |
| Nano Banana 2 | edit | 49 | 3.71 | 63% | 4% | 71% / 12% | 51% | 11 |
| Nano Banana 2 | text | 50 | 3.50 | 60% | 10% | 70% / 22% | 64% | 4 |
| Nano Banana Pro | edit | 50 | 3.28 | 42% | 8% | 60% / 14% | 62% | 6 |
| Nano Banana Pro | text | 50 | 3.14 | 36% | 6% | 56% / 24% | 60% | 3 |

- **Decision: Nano Banana 2, drawing over the strokes.** It has the best mean score, the fewest
  rejections and the most stars, at half Pro's price.
  - Comparing each way's best picture per character, it beats its own text way 8–6 (11 ties) and
    Pro's edit way 11–7 (7 ties).
  - Every character got a star except 月, whose script was wrong (below).
- **The strokes decide the score.** By the strokes answer:
  - *yes*: mean 4.08, and 23 of the 24 stars;
  - *partly*: 2.63;
  - *no*: 1.78, and no star.

  Yes on both questions averaged 4.49, with 95% scored 4–5. *Depicts* matters less: *yes* 3.77,
  *partly* 3.10.
- **Each way fails in its own manner.**
  - **Text breaks the strokes.** Two or more pictures answered strokes *no* in 8 characters (林 森 月
    女 耳 爪 果 炎) by text, against 2 (舟 本) by editing. The breaks were joins that came apart,
    proportions lost (林's trees the same height, 舟 widened), a slanting stroke made straight, and a
    stroke cut short (伞).
  - **Editing over-integrates.** The model works the strokes into the drawing: branches grow from
    木's strokes, earth climbs the trunk, parts of 舟 become the boat. Most of these pictures are
    edit pictures. Its *depicts* is also the weakest (51% yes).
- **The owner's guesses** of which pictures were drawn over the reference were right 26 of 31 times.
  - Guesses made from a stroke error were all right, 爪 and 旦 8 of 8.
  - Guesses made from how well a picture fitted the character were mixed.
- **月's crescent faced the wrong way** in 7 of 8 pictures because its script said "its back on the
  left". The owner wants the waxing moon, curved on the right. That is the script's fault, not the
  models'.
- **Other failures**: people drawn without a face or clothes (子 立); the picture covering strokes
  (禾 E, 米); a stray dot (森 F); dark banks (川 H); the character drawn three times (众 F).

**Answers to questions raised while judging:**
- **Do proportions matter?** Yes, wherever they tell one character from another, and in how the parts
  of a compound share the box.
  - 日 (sun) is tall and 曰 (to say) is wide.
  - 末 (tip) has the longer line on top, while 未 (not yet) has the shorter; 土 and 士 differ the same
    way at the bottom.
  - In compounds the parts are not equal. Read from the pinned strokes, 林's right tree is wider (it
    spans 390–985 of the 1024 box, the left one 65–429) and taller (its trunk runs 71–917, the left
    one's 108–877), and its line across sits higher. The left tree's last stroke shrinks to a dot so
    as not to collide.
  - So in 林 a picture with two equal trees is a little wrong.
  - Stretching a whole character slightly is a difference of typeface, and it still reads. A picture
    meant to teach the shape should keep the reference's box.
- **Does a stroke's direction matter?** Its kind does: horizontal, vertical, a slant to the left (撇), a
  falling stroke to the right (捺), a dot, a turn, a hook.
  - 千 and 干 differ only in whether the top stroke slants.
  - A small tilt is style: horizontals in regular script rise slightly to the right, and verticals
    lean a little.
  - 舟's middle dot drawn straight down is a different kind of stroke, so it is an error.
- **How to judge a picture's strokes**, as a checklist:
  1. the same strokes, each of the same kind;
  2. the same touches, crossings and gaps;
  3. the same hooks and plain ends;
  4. the lengths that tell characters apart kept;
  5. each part in its place, at its size.

  Thickness, a slight tilt and brush texture are style.

### Round 3

What changed, from round 2:
- **Only Nano Banana 2, only drawing over the strokes**, with 8 takes a character, so the page still
  shows 8 pictures.
- **The art direction adds rules against round 2's failures.**
  - The strokes stay plain written strokes, and nothing grows from them.
  - The strokes are on top.
  - Directions and proportions are kept, and every stroke is drawn whole.
  - No stray dot or dark shape sits beside the strokes.
  - The character appears once.
  - People have faces and clothes.
- **The edit prompt says the strokes must lie on the reference's strokes**, at the same size and
  place.
- **月's script turns the crescent round.** The scripts of round 2's other weak characters carry their
  lessons for the later redraw pass: 林's and 森's sizes, 女 facing left, the heart on 心's strokes, 伞's
  whole line, 舟's slanting dots, grains behind strokes, pale banks.
- **Thirty new characters**, their `exact` lines measured on the outlines.
- **The judging page can mark a character to redraw later.**

Not yet drawn.

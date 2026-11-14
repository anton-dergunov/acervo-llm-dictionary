# Writing a stroke script

How to write one character's script for the full run. It holds every rule the owner's judging of
rounds 1–3 produced ([`../README.md`](../README.md), "Rules for later rounds" and "Results"). Read
it whole before writing the first one.

## What the script is for

Nano Banana 2 gets two things: the character's strokes as a black-on-white picture, and a prompt
built from the script ([`../prompts/edit.md`](../prompts/edit.md)). The prompt's art direction
([`../prompts/direction.md`](../prompts/direction.md)) is the same for every character. It already
says: strokes bold and black on top; nothing grows out of a stroke; pale colours; no text, frame or
backdrop; faces and clothes on people. **Do not repeat those rules in a script, and never contradict
them.** The script says what only this character needs: what it depicted, which part each stroke
becomes, and the details of its shape a picture must keep.

The owner picks the best of four pictures, so a script does not need to be clever. It needs to be
**right**: a picture whose strokes are wrong is never chosen, whatever else it gets right.

## The shape

```yaml
目:
  object: an eye, stood upright as the character stands it, with its lids as the frame and its iris between the two inner lines
  history: >-
    The oldest forms drew an eye lying on its side, with the iris in the middle. The modern form
    stood it upright, so the eye's corners are at the top and the bottom.
  layout: >-
    One tall almond-shaped eye fills the frame from top to bottom. Its lids follow the frame's
    strokes. The iris is a soft round shape, pale brown or blue, between the two inner lines, with a
    mid-grey pupil; nothing in it is black.
  exact:
    - The two inner lines touch the left side and stop short of the right side.
    - The top and right side are one stroke, turning down at the top right and ending in a small hook to the left.
  strokes:
    - where: a line down the left side, from the top to the bottom
      part: the eye's left lid
    - where: …one entry per stroke, in writing order…
```

- `object` (one line): what the character depicted, as one concrete picture.
- `history` (one to three sentences): how the oldest form drew it and how the modern form drifted, where
  that helps the picture. Plain facts, no stories.
- `layout` (two to five sentences): how the picture fills the square the way the character fills its
  box; which way things face; where each component's thing sits; colours, kept pale.
- `exact` (a list): the details of the shape a picture must keep, read off the fact sheet. Each item
  is one sentence.
- `strokes` (a list): **exactly one entry per stroke, in the fact sheet's order**. `where` says where
  the stroke lies and how it runs, as the viewer sees it; `part` says what it becomes.

`run.py check <your file>` refuses a script with a wrong stroke count, a missing field, or a digit.

## Rules

**What it depicts comes from the source, never from you.**
- `object` follows the fact sheet's source hint and the character's oldest forms. Never make up a fresh
  mnemonic.
- A **compound** (an ideograph made of components) is one scene made of its components' things: 好 is
  a mother 女 holding her child 子. `object` names the scene and what each component is in it. `layout`
  puts each component's thing on that component's own strokes, side by side or one above the other,
  as in the box. **Add nothing the hint and the components do not name.** Round 3's 坐 turned its 土
  (earth) into a tree, and its pictures depicted poorly.
- A component means what it means: 土 is earth or a mound, 口 a mouth (or an opening), 日 the sun, 月
  the moon (or flesh, ⺼, in body words), 木 a tree, 亻 a person, 扌 a hand, 氵 water, 艹 grass, 宀 a roof, 女 a
  woman, 子 a child, 心 a heart, 目 an eye, 田 a field. Where the fact sheet shows a component's script,
  reuse its parts, adapted to this character's strokes, so the same component looks the same everywhere,
  unless the compound's own hint gives the component another role (土 alone is clay on a potter's wheel,
  by its source; inside a compound it is usually earth or ground). The compound's hint wins.
- When the hint is abstract ("pronoun", "phonetic loan", "a mark"), draw what the components and the
  hint literally show, and let the scene suggest the meaning. If even that is abstract (一, 二, 三, 上),
  draw the simplest real object that matches the hint: a line of the horizon, a stack of bars, a mark
  above a line.
- Name a direction whenever it matters: which way a person or animal faces, which way a crescent
  curves (月 waxes on the right), which way a bow or a boat points. A woman 女 faces left.
- A Traditional and a Simplified form of one character (車 and 车, 國 and 国) share `object` and
  `history`. Their `strokes`, `layout` and `exact` follow each form's own strokes.

**Every stroke is a part, and stays a plain stroke.**
- Each stroke becomes **one** part of the object, lying exactly where the stroke lies. Where a stroke
  has no natural part, make it part of an outline, a frame, a rim, or a line of the ground.
- Never ask for a stroke to become a flame, a drop, a branch, a root tip, a finger or a leaf **growing
  out of** a stroke. The stroke is the part; the rest of the object is drawn behind and around it.
- People always have a face (eyes, nose, mouth) and simple clothes; say so in `layout` whenever there
  is a person.
- Ground, water and grass stay below the lowest stroke unless a stroke *is* the ground.
- Colours are pale and soft; nothing dark next to a stroke. Never ask for anything black.

**`where`, as the viewer sees it, in words.**
- Left is the viewer's left. Say where the stroke lies ("a line across the top of the right half"),
  how it runs ("a sweep from the centre down and out to the bottom left"), and where it starts and ends
  when that matters ("from the middle of the trunk").
- Use the fact sheet's kind: across, down, a sweep down to the left (撇), a falling stroke down to the
  right (捺), a dot, a turn ("across, turning down at the top right"), a hook ("ending in a small hook
  to the left"), a rising stroke ("a short stroke rising to the right").
- **Never a digit, and never number a stroke** ("the third stroke", "S3"). Round 1's numbered strokes
  came back as numbers drawn into the pictures. Name a stroke by where it lies.

**`exact`: what the picture must keep, read off the fact sheet, never from memory.**
- **Touches and crossings** that shape the character: "the trunk crosses the line across", "the inner
  lines touch the left side". Take them from the sheet's measured list.
- **Gaps** the sheet reports as "do NOT touch": they are easy to lose. "The two lower sweeps start at
  the trunk and do not touch each other." "The inner lines stop short of the right side."
- **Hooks and plain ends**: every hooked stroke ("ends in a small hook to the left"), and a vertical
  that a model would like to hook but has none ("a straight vertical ending in a plain point, with no
  hook": 木's trunk, and every 木 inside a compound).
- **Lengths that tell characters apart**, as a comparison **in words**, from the sheet's ratios. Put it
  in `exact` *and* in the stroke's `where`. A ratio of 0.60 is "clearly shorter, a little over half
  as long"; 0.75 "about three quarters as long"; 0.90 or more "about as long". The pairs to watch:
  末/未, 土/士, 日/曰, 己/已/巳, 千/干, 人/入/八, 大/太/犬/天/夭, 王/玉/主, 刀/力, 白/自, 目/且. Round 3's
  未 said only "shorter" and five of eight pictures lost the difference.
- **Sizes and places of a compound's parts**, from the components' boxes: "the left tree is narrower and
  a little shorter than the right". Equal parts are rare; say which is bigger.
- Write as many items as the character needs, usually two to six; a complex character may need more.
  Leave out what any picture keeps anyway.

**Many strokes** (ten or more): still one entry per stroke. Group them by component in your head, and
make the `part`s of one component read together ("the roof's left edge", "the roof's ridge", "the
roof's right edge, turning down"). `layout` says where each component's thing sits.

## Three scripts that worked

Each was starred by the owner, and scored 5.

```yaml
林:
  object: two trees standing side by side, a grove
  history: 'The oldest forms drew two trees side by side: a wood.'
  layout: 'The two trees are not the same size, as in the character: the left tree is narrower and a
    little shorter; the right tree is wider and taller, its trunk starting higher and reaching lower,
    and its branches higher up. The left tree''s right root is short so that it does not reach the
    other tree. Pale leafy crowns surround both treetops, behind the strokes.'
  exact:
  - Both trunks are straight vertical lines ending in a plain point at the bottom, with no hook.
  - The left tree's line across is short and rises a little to the right; it stops before the right tree.
  - The left tree's last stroke is a short dot touching its trunk just below the crossing, not a long sweep.
  - The right tree's two lower sweeps both start where its trunk crosses its line across.
  - The two trees do not touch each other.
  - The right tree is wider and taller than the left; its line across sits higher than the left tree's.
  strokes:
  - where: a line across the upper part of the left half
    part: the left tree's branches
  - where: a long straight line down the middle of the left half
    part: the left tree's trunk
  - where: a sweep from the centre of the left trunk down to the bottom left
    part: the left tree's root, spreading left
  - where: a short dot-like stroke beside the left trunk, slanting down to the right
    part: the left tree's short right root
  - where: a line across the upper part of the right half
    part: the right tree's branches
  - where: a long straight line down the middle of the right half
    part: the right tree's trunk
  - where: a sweep from the centre of the right trunk down to the left
    part: the right tree's root, spreading left
  - where: a sweep from the centre of the right trunk down and out to the bottom right
    part: the right tree's root, spreading right

好:
  object: a mother kneeling on the left, holding her child on the right
  history: 'An ideogram: a woman 女 with a child 子, the good thing.'
  layout: The mother fills the left half and faces right, toward the child; the child fills the right
    half, arms out toward her. Both have friendly faces with eyes, a nose and a mouth, and wear simple
    pale clothes.
  exact:
  - The left part (the woman) and the right part (the child) do not touch.
  - In the woman, the first stroke turns at a sharp angle and sweeps down to the right; the second
    sweep crosses it; the line across rises to the right, crosses the first stroke and ends on the second.
  - In the child, the first stroke runs across and turns down to the left, touching the long vertical;
    the vertical ends in a hook to the left; the line across crosses it.
  strokes:
  - where: a stroke in the left half from the top down to the left, turning sharply to sweep down to the lower right
    part: the mother's head and back, then her lap
  - where: a sweep in the left half from the middle down to the bottom left
    part: the mother's arm, reaching down
  - where: a line across the left half, rising to the right
    part: the mother's other arm, reaching toward the child
  - where: a line across the top of the right half, turning back down to the left
    part: the child's head
  - where: a long line down the right half, ending in a hook to the left
    part: the child's body, the hook its feet
  - where: a line across the right half, below its top
    part: the child's arms, held out wide

人:
  object: a person standing, seen from the front, legs apart
  history: >-
    The oldest forms drew a person in profile, bending slightly forward; the two strokes that
    remain are the body and the legs.
  layout: >-
    The person fills the square from head to feet. The small head sits just above the top of the
    first stroke; the arms hang loosely at the sides and are pale, so that only the body and the
    legs are ink.
  strokes:
    - where: a long sweep from the top centre down and out to the bottom left
      part: the body, running down into the left leg
    - where: a long sweep from the middle of the first stroke down and out to the bottom right
      part: the right leg
```

(人 says "the first stroke": naming a stroke by its order in words is allowed when nothing else
will do, but prefer naming it by where it lies.)

## How to work

1. For each character on your list, read its fact sheet, `out/full/facts/<group>/<character>.md`.
   It gives the source's hint, the components and their boxes, each stroke's kind and place, the
   measured touches, crossings and gaps, the length ratios, and any component script to reuse.
   The sheet numbers strokes S1, S2…, for you only.
2. If the sheet leaves you unsure where a stroke lies, look at its numbered drawing (a PNG beside the
   sheets, named in your task). Do not look at every one; they cost time.
3. Write the script into your own file, in the order of your list.
4. Run `.venv/bin/python experiments/character-pictures/run.py check experiments/character-pictures/scripts/<your file>`
   from the repository root, and fix every problem it reports.
5. Before you finish, reread each script once against its sheet: every stroke in order, every touch
   and gap that matters in `exact`, every length that tells the character apart in words.

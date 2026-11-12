# Writing · practising a word's characters, stroke by stroke

**Built**, as a sheet on every Mandarin word. For a learner of Chinese the characters are the hard part,
and writing one by hand is how it is remembered. The sheet teaches the **correct** way, not just the
final shape: the strokes in the standard order, each in the direction it is written. It works with a
mouse on the laptop, a finger or the Pencil on the iPad, and a finger or a stylus on a phone. The
design of record is the prototype (`design/ui-prototype/`, `?open=图书馆&write=trace`).

## Where it is

**Write**, a brush beside the headword's listen button on the page and on a card, opens the sheet for
that word ([`articles.md`](articles.md), "Readings"). It is offered for a Mandarin word with at least
one Han character, and nowhere else.

It is a sheet in the article rather than a tab beside Loops and Stories, on purpose. A tab earns its
place when there is a queue to work through, which needs attempts recorded and a schedule read from
them. That is the next step, in [`../plans/languages/cjk.md`](../plans/languages/cjk.md), once the sheet
has been used. **Nothing is stored.** A run is forgotten when the sheet closes.

## Three ways to practise

The sheet takes one word, one character at a time: a chip per character, the reading with the current
syllable marked, the meaning, and the word's own listen button. The way chosen is remembered per
device.

- **Watch.** The strokes are written one after another, in order and direction, each numbered at its
  start, with the radical in its own colour. Play, pause, step back and forth, and again.
- **Trace.** The whole character is shown faintly, and you write each stroke over it in ink.
- **Write.** No outline and no characters. The prompt is the reading, the meaning and the sound, and
  the chips show `?` until a character is written. **Peek** shows the outline for a moment.

Accepted strokes become the printed shape as you go, so the character builds up correctly whatever
the hand did. A finished character gets a line such as *6 strokes · 5 right first time · 1 out of
order · precision 84, good*, a dot per stroke, and **Compare**, which lays the line your hand drew over
the model. After the last character, Trace offers **Write it from memory**.

## Why stroke order is checked, and how

The order is a standard (for Simplified, the mainland's GB 13000.1). It is what makes handwriting
proportioned and legible, cursive forms and handwriting input both depend on it, and a fixed sequence
is motor memory that helps a character come back. So the order is enforced by construction: **a drawn
stroke is only ever matched against the next stroke in the order**, and only in the direction it is
written.

The matching is Hanzi Writer's algorithm (MIT), ported into `web/src/writing/match.ts`. A stroke
matches the expected stroke's median, its centre line, when all of these hold:

- it lies near the median on average;
- it starts near the median's start and ends near its end;
- it runs the same way;
- it has the same shape (Fréchet distance after normalising, at five small rotations);
- it is not much shorter.

It is ported rather than depended on for two reasons. Its runtime reads input through mouse events
and the first touch, which knows nothing of a pen and a resting palm. And its quiz only says
"mistake". **The sentence that teaches the order is the one it cannot say**, so a refused stroke is
matched against every other stroke to name what it was:

- *That's stroke 4 — stroke 3 comes first.*
- *Right stroke, other way round — start at the dot.* (A dot pulses where it starts.)
- *Stroke 1 is already written — next is stroke 3.*
- *Not quite — try stroke 3 again.*

After **two** refusals the stroke is shown being written; after **four** it is written in for you and
counted as missed, so nobody is stuck (`writing/practice.ts`). **Show the next stroke** is a hint asked
for, and counts as one.

## Accepted is forgiving; the grade is not

Acceptance is deliberately loose: a stroke may start a quarter of the box from where it should and
still count, because refusing a rough-but-right stroke teaches nothing. Closeness is told back
separately, as a **precision grade** of 0–100 per stroke and its mean per character
(`writing/grade.ts`). It is computed from two things:

- **path**: how far the drawn line runs from the median, as a root mean square measured both ways, so a
  stroke that is close but stops halfway is not called close;
- **ends**: how far it starts and ends from where the brush is set down and lifted.

**The bounds are a first guess**, set from drawing the fixtures. On a pad about 580 px wide, a stroke
off by 2.5% of the box grades about 82 and by 4% about 64. They are to be tuned by hand on the iPad,
which is the only place "that felt like an 80" can be measured.

## Input: pointer events, a pen and a palm

The pad is an SVG in the dataset's own box, taking Pointer Events only (`touch-action: none`, a
captured pointer), like the map and the photo (`writing/WritingPad.tsx`).

- **Palm rejection.** Once a pen has touched the pad, a finger no longer draws on it: the hand resting
  on the glass is a touch too. A pen landing while a touch stroke is under way replaces it, since that
  touch was almost certainly the palm arriving first. A device with no pen draws with a finger.
- **Every point the pen gives.** `getCoalescedEvents` keeps the Pencil's 240 points a second rather
  than the 60 a frame delivers.
- **Ink.** perfect-freehand (MIT) draws the ink as a filled outline shaped by the pen's pressure, so it
  looks like ink. For a mouse or a finger it simulates pressure from speed. The ink is the text colour:
  black on paper, light in the dark theme. A refused stroke turns red and fades.

If the Pencil turns out finicky in the hand, the variants go behind a picker to be tried, as the
carousel was settled, rather than being tuned by guesswork.

## The data

The strokes are **Make Me a Hanzi's**, as packaged by `hanzi-writer-data` 2.0.1: about 9,500
characters, Simplified and Traditional. Each stroke has an outline, the shape a brush leaves, and a
median in writing order, in a 1024-unit box. The data is under the **Arphic Public License**, which
allows redistribution; the licence travels with it into the image and the test fixtures.

- **Pinned, not generated, and not in the database.** `deploy/acervo/strokes/pin.json` names the
  version and the tarball's digest. `fetch.py` beside it verifies the tarball and writes one file per
  character into the server image while it is built, in a layer above Acervo's code
  ([`../operations/deployment.md`](../operations/deployment.md)). It is the same for every owner and is
  rebuilt rather than backed up.
- **`GET /strokes?characters=`** answers a batch of up to 200. A character the dataset lacks comes back
  in `missing` and writes an activity line naming it. A server built without the data refuses with
  `503 strokes_unavailable`, and `admin log --failed` shows both.
- **On the device**, the strokes are kept in their own IndexedDB database, `acervo-strokes`, beside the
  replica, the dictionaries and the media (`writing/strokeStore.ts`). After every pull, the characters
  of every Mandarin word that the device lacks are fetched: a few hundred characters, about a megabyte.
  So **the sheet works offline** for the owner's own words. Each record is keyed by the dataset and the
  character, so it needs no invalidation, and what an earlier pin left is deleted on open. A character
  the dataset lacks is kept as a record with no strokes, so it is not asked for again. The client's
  dataset name is held equal to the pin by a test.
- **Offline and not yet on the device**, the sheet says so in one line and still shows the word.

### Traditional characters

The dataset covers Traditional shapes, so a `zh-Hant` word works the same way. Its stroke order follows
the mainland convention, which for some characters differs from the order taught in Taiwan (the
Ministry of Education standard). Teaching that order would need a second dataset; it is a line in
[`../plans/languages/cjk.md`](../plans/languages/cjk.md), worth doing only if Traditional is ever
learned in earnest.

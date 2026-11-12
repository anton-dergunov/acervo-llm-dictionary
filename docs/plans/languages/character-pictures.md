# Pictures over pictographic characters · an experiment first

**Status:** round 1 of the experiment is judged
([`experiments/character-pictures/`](../../../experiments/character-pictures/README.md)). The idea
works: 18 of 22 characters got a picture the owner liked, and most failures came from the prompt,
which has been tightened. Round 2 (20 new characters and five redraws) is prepared for the owner to
draw. Written down when the Write sheet was built
([`../../features/writing.md`](../../features/writing.md)), as the owner's next idea for the characters.

## The idea

Some characters began as drawings: 人 a person, 山 three peaks, 水 a stream with water splashing
from it, 木 a tree. These are pictographs (象形字), with simple ideograms (指事字) beside them. For
such a character, a picture of what it depicts, **drawn so that its strokes are the character's
strokes**, makes the shape mean something: the person whose legs are the two strokes of 人. It would
be an extra card in the word's article — the page and the cards — for each such character, not part of
the Write sheet, where it would be a distraction.

Two limits come with it, and each would cost trust if ignored:

- **Only characters that really are pictures.** Most characters are phono-semantic compounds
  ([`cjk.md`](cjk.md)). 花 is 艹 for meaning plus 化 for sound, not a drawing of a flower, and a
  picture laid over it would teach a false etymology. A character gets a picture only if a source
  says it is pictographic or a simple ideogram, and never because a model thinks so.
- **The historical form is the reference, not invention.** Where the modern form has drifted from the
  drawing (水's splashes are its side strokes), the picture follows what the character depicted, not
  a fresh mnemonic.

## The experiment

Whether any image model can do this at all is the open question, and it is answered before anything
is built. It lives in [`experiments/character-pictures/`](../../../experiments/character-pictures/README.md),
scored on its own page (as every labelling follow-up is).

- **Characters.** 22 whose modern form still looks like the object: 人 大 从 休 山 水 木 林 森 口 日 月
  明 火 雨 田 门 竹 井 册 羊 凸. They include compounds (林 森 明 休 从), to see whether composition survives.
  鱼 马 鸟 and 目 are left out because simplification or rotation erased the drawing.
- **What each depicts.** Make Me a Hanzi's `dictionary.txt` (LGPL-3.0 or later, checked) carries an
  etymology per character: its type and a hint of what it shows. That is the source of the
  selection. 刀 has none there and was replaced by 凸.
- **A stroke script per character.** Asked plainly, a chat image model pastes the character onto a
  scene. Told which stroke is which part, it draws 人 and 大 right. So every prompt carries, for each
  stroke, where it lies and which part of the object it becomes, written from the source's hint and
  the oldest forms.
- **Models.** Nano Banana 2 and Nano Banana Pro on Vertex, and a sample on Cloudflare's FLUX.2 klein,
  which the free allowance limits. Each is asked at its family's own settings and not ranked against
  the others.
- **Two ways to ask.** By text alone, and by editing: the character's strokes are rendered from the
  stroke data the server already holds, **each stroke in its own colour**, named in the prompt.
- **Judged blind** by the owner: a 1–5 score per picture, one starred best per character, and two
  questions per picture — do the strokes stay where the character's strokes are, legible as the
  character; does the picture show what the character really depicts. (Round 1 also asked whether
  it would help to remember the character; that was too subjective to answer apart from the score.)

The likeliest outcomes are that editing works for the simplest pictographs and nothing else, or that
nothing works well enough. Either is an answer: the first sizes a small feature, and the second
closes this plan.

## The full run, after round 2

If round 2 holds up, every pictographic or ideographic character in the source gets pictures:
around 3,300 characters. The choice between Nano Banana 2 and Pro is made from round 2, since the
full run costs per picture. Judging that many must be quick:

- **One character at a time, its pictures side by side**, each marked **good**, **usable but not
  perfect**, or **not usable**. There are no questions and no 1–5 score.
- **Regeneration by priority.** A rerun first redraws characters with nothing usable, then those
  with only usable-but-not-perfect pictures, and leaves characters that have a good one.
- **A check that strokes are correct** before a picture is shown in an article. A joined or hooked stroke
  is easy to miss at a glance, as round 1 showed for 月 and 明.

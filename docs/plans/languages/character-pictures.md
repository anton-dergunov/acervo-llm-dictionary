# Pictures over pictographic characters · an experiment first

**Status:** not started. Written down when the Write sheet was built
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
is built. It lives in `experiments/character-pictures/` when run, scored on its own page
(as every labelling follow-up is).

- **Characters.** About twenty with an undisputed pictographic origin: 人 大 山 水 木 口 目 日 月 火 雨 田
  鱼 马 门 刀 牛 羊 鸟 竹, plus two compounds of them (林, 明), to see whether composition survives.
- **What each depicts.** Make Me a Hanzi's `dictionary.txt` carries an etymology per character: its
  type (pictographic, ideographic, pictophonetic) and a hint of what it shows. That is the source of
  both the selection and the prompt; its licence is checked before it is used.
- **Models.** Every image model the owner has a provider for, including Gemini's image models
  ("Nano Banana"), each at the settings its own experiment finds best, not ranked against each other.
- **Two ways to ask.** By text alone ("a standing person whose two legs form the character 人"), and by
  editing: the character's own strokes rendered from the stroke data the server already holds,
  handed to the model as the image to draw over. The second is the likelier to keep the strokes where
  they are, and is the reason this needs the stroke data at all.
- **Judged on two questions**, by the owner, per picture: do the strokes stay where the character's
  strokes are, legible as the character; and does the picture show what the character really
  depicts.

The likeliest outcomes are that editing works for the simplest pictographs and nothing else, or that
nothing works well enough. Either is an answer: the first sizes a small feature, and the second
closes this plan.

You write one stroke script for a Chinese character, following the guide after this brief exactly.

A stroke script tells an image model how to draw the character's object so that the character's own
strokes are parts of the picture. Read the guide whole: it holds every rule the owner's judging of
the earlier rounds produced.

You get the fact sheet (the strokes measured from the stroke data, the hint from Make Me a Hanzi,
the components with the scripts already written for them), the "Glyph origin" section of the
character's English Wiktionary entry as wikitext (sometimes also that of a related Traditional or
Simplified form), and the numbered drawing of the strokes. The drawing's numbers are the fact sheet's
S1, S2…, for you only: never write a number into the script.

## What the character depicts comes from the origin

Wiktionary summarises current scholarship and cites it; the fact sheet's hint is sometimes the
traditional folk explanation instead (王 is "a man joining heaven and earth" there, where scholars
read the head of a ceremonial axe). Follow the origin where it gives a reading; where it gives none,
follow the hint and the components. Add nothing that none of them names. Its templates:
- `{{liushu|p}}` a pictogram (象形); `{{liushu|i}}` a simple ideogram (指事); `{{liushu|ic}}` an
  ideogrammic compound (會意); `{{liushu|psc}}` a phono-semantic compound (形聲); `{{liushu|j}}` a
  phonetic loan (假借): borrowed for its sound, so what it depicts is what its form first drew.
- `{{Han compound|A|B|ls=…|c1=…|c2=…|t1=…|t2=…}}`: the character is made of A and B. `ls=ic` an
  ideogrammic compound, `ls=psc` a phono-semantic compound, `ls=p` a pictogram drawn as one
  picture of those parts; `cN=s` marks component N as semantic (meaning), `cN=p` as phonetic
  (sound); `tN=` is its gloss.
- `{{zh-ref|…}}` cites a scholar; `{{Han etyl}}` stands for a table of the ancient forms; `{{zh-l|X}}`,
  `{{m|zh|X}}`, `[[X]]` name another character.

**Drop** the character instead of writing it when the origin says it is a phono-semantic compound
(one component for meaning, one for sound) and gives no pictographic or ideographic reading of it:
its picture would teach a false etymology. Never drop an ideogrammic compound (會意), a phonetic loan,
or a character for which the origin also gives a pictographic or ideographic reading. A Simplified form
drawn from cursive script depicts what its Traditional form depicts; the fact sheet names the
counterpart's script when there is one, and the two share `object` and `history`.

## The answer

One YAML block and nothing after it:

```yaml
verdict: write
origin: what the origin says the character first depicted and how it is classed, and whom it cites, in one sentence
reason: what the picture shows and why, in one sentence
script:
  object: …
  history: …
  layout: …
  exact:
    - …
  strokes:
    - where: …
      part: …
```

`strokes` has exactly one entry per stroke, in the fact sheet's order. For `drop`, give `verdict`,
`origin` and `reason`, and no script.

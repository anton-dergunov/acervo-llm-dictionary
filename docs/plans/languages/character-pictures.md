# Pictures over pictographic characters · the full run

**Status:** the experiment is done
([`experiments/character-pictures/`](../../../experiments/character-pictures/README.md)): over three
rounds, the idea works and the way is settled. Round 3 gave every one of its 31 characters a picture
the owner scored 5. **The full run is under way**: every other pictographic or ideographic character
of the commonest 3,000 whose scholarly origin confirms it, drawn six times each and chosen on the
tablet. What is left is at the end. Written down when the
Write sheet was built ([`../../features/writing.md`](../../features/writing.md)), as the owner's next
idea for the characters.

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

- **Characters.** Round 1 took 22 whose modern form still looks like the object: 人 大 从 休 山 水 木 林 森 口 日 月
  明 火 雨 田 门 竹 井 册 羊 凸. They include compounds (林 森 明 休 从), to see whether composition survives.
  Rounds 2 and 3 added 50 more, half of them compounds.
- **What each depicts.** Make Me a Hanzi's `dictionary.txt` (LGPL-3.0 or later, checked) carries an
  etymology per character: its type and a hint of what it shows. That is the source of the
  selection. 刀 has none there and was replaced by 凸.
- **A stroke script per character.** Asked plainly, a chat image model pastes the character onto a
  scene. Told which stroke is which part, it draws 人 and 大 right. So every prompt carries, for each
  stroke, where it lies and which part of the object it becomes, written from the source's hint and
  the oldest forms.
- **Models.** Nano Banana 2 and Nano Banana Pro on Vertex in rounds 1–2, and a sample on Cloudflare's
  FLUX.2 klein in round 1, which the free allowance limits. Klein was dropped after round 1 and Pro
  after round 2. Since round 3 only Nano Banana 2 draws.
- **The way to ask: editing.** The character's strokes are rendered in solid black on white from the
  stroke data the server already holds, and sent with the stroke script as the prompt.
  - Rounds 1–2 also asked by text alone. Round 2 showed it breaks the strokes far more often: in 8 of
    25 characters, against 2 when editing.
- **Judged blind** by the owner: a 1–5 score per picture, one starred best per character, and two
  questions per picture — do the strokes stay where the character's strokes are, legible as the
  character; does the picture show what the character really depicts. (Round 1 also asked whether
  it would help to remember the character; that was too subjective to answer apart from the score.)

**The answer.** It works, and not only for the simplest pictographs.
- Round 3 drew 31 characters, 14 of them compound ideographs (好 男 看 坐), 8 takes each. Every one got
  a picture scored 5: 1.71 per character on average.
- The strokes decide a picture's score. Of 31 stars, 29 went to pictures whose strokes were judged
  right, and none to one whose strokes were wrong.
- The details still hardest to keep are lengths that tell characters apart, such as 未 against 末.

## The full run

**Which characters.** Every character Make Me a Hanzi calls pictographic or ideographic and the pinned
stroke data has: 2,067. Rounds 1–3 drew 72, which leaves 1,995. They are put in four groups by how often
they are written in Simplified Chinese, Traditional Chinese or Japanese, whichever is highest:
- g1, the top 1,000: 584 characters;
- g2, 1,000 to 2,000: 410;
- g3, 2,000 to 3,000: 254;
- g4, the rest: 747. **Not drawn**: a learner aiming at moderate Chinese almost never meets a
  character outside the top 3,000, and even HSK 3.0's full syllabus stops there.

They are drawn and chosen in that order: 1,248 characters in all, less those the scholarly origin
rules out (below).

**Checked against scholarship.** Make Me a Hanzi's hint is sometimes a traditional folk explanation:
王 is "a man joining heaven and earth" there, where scholars read the head of a ceremonial axe. And
the scripts' scenes were written by models from their own knowledge, some inventing things (會's
hall). So every script is checked by Argon against the "Glyph origin" of the character's English
Wiktionary entry, which summarises current scholarship and cites it (95% of g1–g3 have one that says
what the character is).
- Argon keeps a script, corrects its object and history (and the parts that follow from them), or
  **drops** a character the origin calls phono-semantic with no pictographic or ideographic reading:
  its picture would teach a false etymology, the first limit above.
- The strokes stay bound by the fact sheet: a correction may not change where any stroke lies.
- Of g1's 584: 248 kept, 144 corrected (王 an axe head, 古 a shield over a mouth, 具 hands lifting a
  cauldron), **192 dropped** (深, 命, 字, 會…). Make Me a Hanzi's "ideographic" is often a
  phono-semantic compound in current scholarship.
- g2 and g3 are written by Argon from the same fact sheets and origin, then checked the same way.
- About $0.016 a check in batch, measured.

**Shared across languages.**
- A picture belongs to a character's strokes, so it serves every language that writes the character
  that way. 人 serves Chinese and Japanese; 車 serves Traditional Chinese and Japanese.
- Korean hanja are the Traditional forms, so they are covered too.
- Not covered:
  - **Japanese-only forms.** 285 of the 2,500 commonest Japanese kanji (気 歩 黒 戸 亀 …) are not in
    the pinned stroke data. About a hundred of them would be pictographic or ideographic. Covering
    them needs a Japanese stroke source (KanjiVG, CC BY-SA 3.0) pinned beside Make Me a Hanzi, and an
    etymology source for them. Many are variants of characters drawn here (戸 and 户, 亀 and 龟), so
    their scripts would adapt existing ones.
  - **Shared characters whose Japanese form differs** in a detail (角, 骨, 直): their pictures follow
    the mainland strokes.

**How.**
- Nano Banana 2 draws over the strokes, as in rounds 2 and 3.
- **Six takes a character**, the owner's choice once the checks proved cheap and the drops shrank
  the run. In round 3, a character had a picture scored 5 within four of its eight takes 67% of the
  time, and one scored 4 or more 90% of the time; six gives more to choose from.
- **In Vertex batch jobs**: half the price ($0.034 a picture, measured), and no limit of one picture a
  minute.
- About $200 for the characters left after the drops at six takes, Argon's checking and writing
  about $40, and what remains of the account's $295 cap for redraws.
- The scripts are written from measured fact sheets, by a brief that carries every rule the rounds
  produced (`scripts/GUIDE.md` in the experiment).

**Choosing.** The owner's page shows one character at a time with its pictures. A tap stars the
best; "none good — redraw" asks for four more, with an optional note saying what is wrong. Nothing is
scored, unlike the rounds. This replaces the "good / usable / not usable" marks this plan first had in
mind: only the best picture is ever shown, so only the best needs marking.

## What is left

In this order. Every Google Cloud call bills the one account the experiment's ignored
`billing.local.json` names (project, account and profile, checked on every request), and never more
than its cap.

1. **Finish the full run**: `full_run.sh` in the experiment, one command, safe to rerun. It
   fact-checks g1 (done), draws it while Argon writes g2 and g3, checks those and draws them.
2. **Choose**, on the tablet, and **redraw** the marked characters after revising their scripts
   from the notes.
3. **The feature**:
   - Tap a character in a Chinese headword for a card with its picture, what it depicted, its
     components and a link to the Write sheet. Or show the word's characters as a row of thumbnails
     under the headword.
   - About 80% of characters are sound-plus-meaning compounds with no picture of their own. Their
     card shows their components' pictures (妈: 女's picture, "sounds like 马"), so nearly every
     character a learner meets gets some picture. Measure that coverage first.
   - The chosen pictures ship as pinned data fetched to the device, like the strokes: one picture a
     character, about 30 KB, so about 40 MB in all.
   - A picture's ink can be compared with the character's strokes by machine (the pilot inked 93–98%
     of them), to flag a broken picture before it is shown.
4. **Japanese-only forms**, if Japanese is learned in earnest (above).

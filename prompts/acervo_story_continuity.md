# Who and where, in each picture of a story

You are given a short illustrated story: for each part, its text and the brief its picture was
drawn from. One picture sits above each part.

Later pictures will be drawn with earlier ones as references, so that a person who appears again
looks like the same person and a place that appears again looks like the same place. Your job is to
say **which people and which place each picture shows**, with stable ids, so the right earlier
picture can be chosen — and, just as important, so the wrong one is not. Sending the picture of one
man as a reference for a different man paints the first man's face onto the second.

Return one JSON object and nothing else. No prose, no code fences.

## The shape

```json
{
  "characters": [
    {"id": "spencer", "description": "a man of about forty, curly brown hair, round glasses, white lab coat over a navy shirt"},
    {"id": "art_fry", "description": "a man in his fifties, swept-back grey hair, dark suit"}
  ],
  "scenes": [
    {"id": "lab", "description": "a cluttered 1960s chemistry laboratory, shelves of bottles, wooden benches"},
    {"id": "church", "description": "a wood-panelled church with rows of pews"}
  ],
  "parts": [
    {"characters": ["spencer"], "scene": "lab", "change": ""},
    {"characters": ["art_fry"], "scene": "church", "change": ""},
    {"characters": ["spencer", "art_fry"], "scene": "lab", "change": "several years later; Spencer is greyer, and the lab is half on fire"}
  ]
}
```

- `characters` — every person or animal **drawn** in at least one picture, once each.
- `scenes` — every place a picture is set in, once each.
- `parts` — one entry per part, in order, one for every part you are given:
  - `characters`: the ids of who is **visible in that picture** — read the brief, not only the text.
    Someone the text mentions but the brief does not put in frame is not in it.
  - `scene`: the id of the one place that picture is set in.
  - `change`: what is different about these people or this place since they were last drawn, in a
    short phrase — time that has passed, someone older or hurt, a room now wrecked, night instead
    of day. Empty when nothing has changed or nothing here was drawn before.

## The rules that matter

**One id is one individual.** Two different people are two ids even when they have the same job,
the same age or the same role in the story — a second scientist, a new employee, another dog. Only
give a later picture the same id when it is really the same person, the one a reader would
recognise. This is the rule whose failure does the most damage.

**A scene is one physical place.** The same laboratory later, even on fire or in ruins, keeps its
id, and the difference goes in `change`. A different room, a different building, a street outside
the lab — those are different scenes. **Before you give a part a new scene id, check whether an
earlier part is already set there**: "the lab", "his old lab", "back at the laboratory years later"
are one scene. A place that is only glimpsed through a window does not count.

**Crowds and passers-by are not characters.** Only someone who could matter again gets an id.

**ids are short lowercase slugs**: `spencer`, `the_dog`, `bakery`, `old_house`. Use a name when the
story gives one, spell each id identically everywhere, and declare every id a part uses.

**Describe what a camera would see.** A `description` is what makes the person or place
recognisable — age, build, hair, clothing, colours; layout, materials, light — taken from the
briefs. Do not invent what the briefs do not say.

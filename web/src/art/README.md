# The make dialogs' pictures

One small WebP per catalogue id, read by `../art.tsx`:

- `styles/` — a sample of each picture style in `config/image-styles.yaml`: one subject, drawn with
  that style's own brief.
- `kinds/` — a vignette for each kind of story in `config/story-types.yaml`.
- `music/` — a vignette for each of LexiBeat's bed families.

**Made for this project**, by the owner, with Google's Gemini image model on the owner's own Google
Cloud account, from the prompts in `design/dialog-art.yaml`. No third-party artwork or photograph is
in them. They are the project's own and are covered by the repository's licence.

**Redrawing one**: `.venv/bin/python scripts/draw_dialog_art.py --only styles/pixel-art`. Run with no
arguments, it draws whatever id has no picture yet — a style added to the table, a kind added to the
config — and writes a contact sheet to `output/dialog-art/sheet.html` to look at before committing.
The same files are mirrored into `design/ui-prototype/img/art/`.

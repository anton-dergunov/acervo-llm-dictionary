# Carousel spike: choosing a picture from a catalogue

The loop and story dialogs choose a music style, a kind of story and a picture style from a row of
pictures (`docs/features/loops.md` §2.18, `docs/features/stories.md`). Three rows have shipped, and
all three were finicky:

1. A wheel that stepped one picture per notch's worth of travel.
2. A native snapping row that was steered back to its choice.
3. Embla.

This spike puts eight approaches side by side, to be tried by hand on the desktop and the iPad. One is
kept, or the row is replaced by something else.

## Why Embla "goes back"

With Embla's default `skipSnaps: false`, a release fast enough to count as a flick goes to the picture
next to the one the drag **started** on (`DragHandler.allowedForce` in `embla-carousel`). So a drag
across three pictures that is let go while still moving jumps back to the first one's neighbour. The
wheel plugin fakes a pointer drag and release, so the wheel takes the same path. A gentle turn is
released below the flick threshold and settles on the same picture again.

A Playwright run against the spike page reproduces this in Chromium:

| Input | Embla as shipped | Embla with `skipSnaps: true` |
|---|---|---|
| Touch fling across three pictures | 1 picture | 9 pictures, with momentum |
| Mouse drag across three pictures, released moving | 1 picture | 3 pictures |

## The eight variants

All of them are under `web/src/carousels/`.

| # | id | What it is |
|---|---|---|
| 1 | `embla` | The row as shipped: the baseline. |
| 2 | `embla-fixed` | The same row, with `skipSnaps: true`. |
| 3 | `native` | A native scroller with CSS `scroll-snap-type: x mandatory`. The browser does all the moving. The code never scrolls the row in answer to a scroll. |
| 4 | `native-one` | `native` plus `scroll-snap-stop: always`: at most one picture per swipe. |
| 5 | `swiper` | Swiper (MIT): free mode with sticky snapping, and its own wheel handling. |
| 6 | `swiper-step` | Swiper paged: one picture per short swipe, and one per wheel gesture. |
| 7 | `strip` | A plain scrolling strip. Scrolling never chooses; a tap does. |
| 8 | `tile` | No row: the chosen picture with ‹ ›, and a press to open the All grid. |

In rows 1 to 6, the picture nearest the middle is chosen as it passes. A tap, ← → and the ‹ › buttons
glide the row without choosing what it passes.

## How to try them

- **In the real dialogs.** A "Carousel on trial" picker sits at the top of every make dialog. The
  choice is per device, and Safari and the installed app on the iPad each keep their own.
- **Without the server**: `/?spike=carousel` shows a make dialog with all three catalogues, drawn
  from the bundled pictures.

For each variant, try:
- a slow swipe;
- a fast flick;
- a drag past several pictures, then let go while still moving;
- a drag that leaves the row;
- a tap.

On the desktop, also try the sideways wheel slowly and quickly, and a drag with the mouse button
held.

## When one is chosen

- Delete the other variants, `CarouselPicker`, `CarouselSpike`, the `?spike=carousel` branch in
  `main.tsx`, `variants.ts` and its test.
- Delete whichever of `embla-carousel-react`, `embla-carousel-wheel-gestures` and `swiper` is no longer
  used, and Embla's builds under `design/ui-prototype/vendor/` if it goes.
- Move the winner's rules from `spike.css` into `styles.css`, and into the prototype in the same change.
- Rewrite the `ChoiceCarousel.tsx` header, `docs/features/loops.md` §2.18 and the carousel paragraph of
  `docs/features/stories.md` to describe the winner, keeping the reason the others lost.
- Remove this plan.

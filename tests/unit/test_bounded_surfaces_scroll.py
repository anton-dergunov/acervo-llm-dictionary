"""Every surface that can hold more than fits on a screen must be bounded and must scroll.

Neither the settings dialog nor the add sheet was. Both declared `overflow: hidden` with no height
limit, which is harmless while the contents are short and silently fatal once they are not: the
surface grows past the window and its own title and buttons become unreachable. It happened twice,
so the shape is now a contract shared by the settings overlay and the composer.

The fix has two halves and needs both. A bound without a scrolling body just clips; a scrolling body
without a bound never overflows, so it never scrolls. And the body must be allowed to shrink — a
flex item defaults to `min-height: auto` and refuses to go below its content, which reintroduces the
clipping through the back door.
"""

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
APP = ROOT / "web" / "src" / "styles.css"
PROTOTYPE = ROOT / "design" / "ui-prototype" / "acervo.css"


def declarations(stylesheet: pathlib.Path, selector: str) -> dict[str, str]:
    text = re.sub(r"/\*.*?\*/", "", stylesheet.read_text(), flags=re.S)
    start = text.index(f"\n{selector} {{")
    body = text[text.index("{", start) + 1:text.index("}", start)]
    found = {}
    for declaration in body.split(";"):
        name, _, value = declaration.partition(":")
        if name.strip() and value.strip():
            found[name.strip()] = value.strip()
    return found


# ── the dialogs ──────────────────────────────────────────────────────────
# The smaller dialogs — a picture, a clip, a loop, a story — share the `.settings` shell.

def test_a_dialog_is_bounded_by_the_window():
    dialog = declarations(APP, ".settings")
    assert "max-height" in dialog, "the dialog can grow past the screen again"
    assert "100%" in dialog["max-height"] or "vh" in dialog["max-height"]
    assert dialog.get("display") == "flex"
    assert dialog.get("flex-direction") == "column"


def test_a_dialog_body_scrolls_rather_than_clipping():
    body = declarations(APP, ".settings-body")
    assert body.get("overflow-y") == "auto", "content taller than the dialog is unreachable"
    assert body.get("min-height") == "0"
    assert body.get("overscroll-behavior") == "contain"


def test_a_dialog_header_does_not_scroll_away():
    assert declarations(APP, ".settings header").get("flex") == "none"


# ── the Settings window ──────────────────────────────────────────────────
# Sized by the screen, never by the page in it: a page switch must not move or resize anything.

@pytest.mark.parametrize("stylesheet", [APP, PROTOTYPE], ids=lambda path: path.name)
def test_the_settings_window_has_a_height_of_its_own(stylesheet):
    window = declarations(stylesheet, ".settings-window")
    assert "dvh" in window.get("height", ""), "a window sized by its content resizes on every page"
    assert "dvh" in window.get("max-height", "")
    assert window.get("overflow") == "hidden"


@pytest.mark.parametrize("stylesheet", [APP, PROTOTYPE], ids=lambda path: path.name)
def test_the_list_and_the_page_each_scroll_on_their_own(stylesheet):
    scroll = declarations(stylesheet, ".prefs-scroll")
    assert scroll.get("overflow-y") == "auto"
    assert scroll.get("min-height") == "0", "a flex item will not shrink below its content without this"
    assert scroll.get("overscroll-behavior") == "contain"
    assert declarations(stylesheet, ".prefs-head").get("flex") == "none"
    column = declarations(stylesheet, ".prefs-side, .prefs-main")
    assert column.get("min-height") == "0" and column.get("flex-direction") == "column"


# ── the composer ─────────────────────────────────────────────────────────
# Both stylesheets, because the prototype is the design and they change together.

@pytest.mark.parametrize("stylesheet", [APP, PROTOTYPE], ids=lambda path: path.name)
def test_the_composer_is_a_bounded_column(stylesheet):
    composer = declarations(stylesheet, ".composer")
    assert composer.get("display") == "flex"
    assert composer.get("flex-direction") == "column"
    # It fills what contains it rather than sizing to its contents, which is what gives the body
    # something to scroll inside.
    assert composer.get("height") == "100%"
    assert composer.get("min-height") == "0"


@pytest.mark.parametrize("stylesheet", [APP, PROTOTYPE], ids=lambda path: path.name)
def test_the_composer_body_is_the_only_thing_that_scrolls(stylesheet):
    body = declarations(stylesheet, ".composer-body")
    assert body.get("overflow-y") == "auto"
    assert body.get("min-height") == "0", "a flex item will not shrink below its content without this"
    assert body.get("overscroll-behavior") == "contain"
    # The region around a composer must not scroll too, or the pinned bars drift out of view.
    assert declarations(stylesheet, ".main.composing").get("overflow") == "hidden"


@pytest.mark.parametrize("stylesheet", [APP, PROTOTYPE], ids=lambda path: path.name)
def test_the_composer_head_and_actions_stay_put(stylesheet):
    assert declarations(stylesheet, ".composer-head").get("flex") == "none"
    assert declarations(stylesheet, ".composer-actions").get("flex") == "none"


@pytest.mark.parametrize("stylesheet", [APP, PROTOTYPE], ids=lambda path: path.name)
def test_the_editor_takes_the_height_instead_of_nesting_a_second_scrollbar(stylesheet):
    fill = declarations(stylesheet, ".composer-body.fill")
    assert fill.get("overflow") == "hidden", "two scroll regions for one document"
    assert declarations(stylesheet, ".composer-body.fill .code-scroll").get("min-height") == "0"

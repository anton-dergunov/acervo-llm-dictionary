"""What a script writer needs to know about one character, measured from the pinned stroke data.

A stroke script says, for every stroke, where it lies and which part of the object it becomes, and
lists in `exact` the details a picture must keep: which strokes touch, cross or stand apart, which
end in a hook, which lengths tell the character apart, how big each part of a compound is. Round 1's
pictures broke exactly those details, and judging them by eye from memory got some wrong (月's inner
lines). So they are measured here, and the writer reads them off a fact sheet:

- **kind and place** of each stroke, from its median (the line a brush follows), in the viewer's
  terms: across, down, a sweep down to the left, a turn, a hook, a dot; where it starts and ends;
- **touches, crossings and small gaps**, from each stroke rendered alone and compared with the others;
- **lengths** of strokes running the same way, as ratios;
- **components** (Make Me a Hanzi's decomposition and its stroke-to-component `matches`), each with
  its box, and the script already written for that component, to reuse;
- the source's etymology, definition and how common the character is in each language.

The sheets number the strokes, for the writer only. A script never does, and nothing numbered is
ever sent to a model (README, "Rules for later rounds").
"""

from __future__ import annotations

import io
import math
from typing import Any

import numpy as np

BOX, TOP = 1024, 900
SCALE = 4                     # masks are 256 px: one pixel is 4 units of the 1024 box
END_RADIUS = 7                # px around a median end that counts as that stroke's end
GAP_LIMIT = 16                # px: report a gap up to this (about 6% of the box)
DENSE_GAP_LIMIT = 9           # px, above eight strokes, where most strokes are near another (3.5%)

# Side forms a compound writes in place of the full component.
SIDE_FORMS = {
    "亻": "人", "扌": "手", "氵": "水", "忄": "心", "艹": "艸", "讠": "言", "訁": "言", "钅": "金",
    "釒": "金", "饣": "食", "飠": "食", "纟": "糸", "糹": "糸", "礻": "示", "衤": "衣", "犭": "犬",
    "刂": "刀", "攵": "攴", "灬": "火", "罒": "网", "⺮": "竹", "辶": "辵", "阝": "阜 or 邑",
    "冫": "冰", "⺼": "肉", "爫": "爪", "彳": "行", "王": "玉", "⺈": "刀", "𠂉": "人", "⺌": "小",
}

IDS_ARITY = {"⿰": 2, "⿱": 2, "⿲": 3, "⿳": 3, "⿴": 2, "⿵": 2, "⿶": 2, "⿷": 2, "⿸": 2,
             "⿹": 2, "⿺": 2, "⿻": 2}
IDS_NAMES = {"⿰": "left | right", "⿱": "top / bottom", "⿲": "left | middle | right",
             "⿳": "top / middle / bottom", "⿴": "surrounding / inside", "⿵": "open at the bottom",
             "⿶": "open at the top", "⿷": "open on the right", "⿸": "wrapping from the top left",
             "⿹": "wrapping from the top right", "⿺": "wrapping from the bottom left",
             "⿻": "overlapping"}


# ── geometry ───────────────────────────────────────────────────────────────


def view(point: list[float]) -> tuple[float, float]:
    """A stroke-data point (y up, from −124 to 900) in the viewer's square: x right, y down, 0–1024."""
    return float(point[0]), float(TOP - point[1])


def _simplify(points: list[tuple[float, float]], epsilon: float) -> list[tuple[float, float]]:
    """Ramer–Douglas–Peucker: the polyline's main turns."""
    if len(points) < 3:
        return points
    (x1, y1), (x2, y2) = points[0], points[-1]
    length = math.hypot(x2 - x1, y2 - y1) or 1.0
    distances = [abs((y2 - y1) * x - (x2 - x1) * y + x2 * y1 - y2 * x1) / length for x, y in points[1:-1]]
    index = max(range(len(distances)), key=distances.__getitem__)
    if distances[index] <= epsilon:
        return [points[0], points[-1]]
    split = index + 1
    return _simplify(points[: split + 1], epsilon)[:-1] + _simplify(points[split:], epsilon)


def _direction(dx: float, dy: float) -> str:
    """A segment's direction in words, as the viewer sees it (y down)."""
    angle = math.degrees(math.atan2(dy, dx))  # 0 right, 90 down, ±180 left, −90 up
    if -12 <= angle <= 22:
        return "across to the right" if angle > -5 else "across, rising slightly to the right"
    if -50 <= angle < -12:
        return "up to the right"
    if 22 < angle < 68:
        return "down to the right"
    if 68 <= angle <= 112:
        return "down"
    if 112 < angle <= 165:
        return "down to the left"
    if angle > 165 or angle < -160:
        return "to the left"
    if -160 <= angle < -112:
        return "up to the left"
    return "up"


def _turn(a: tuple[float, float], b: tuple[float, float]) -> float:
    """The angle in degrees between two segment vectors."""
    dot = a[0] * b[0] + a[1] * b[1]
    norm = (math.hypot(*a) * math.hypot(*b)) or 1.0
    return math.degrees(math.acos(max(-1.0, min(1.0, dot / norm))))


def stroke_shape(median: list[list[float]]) -> dict[str, Any]:
    """Kind of stroke: its direction, its turns, a hook at its end, or a dot."""
    points = [view(p) for p in median]
    length = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(points, points[1:]))
    main = _simplify(points, 30.0)
    segments = [(b[0] - a[0], b[1] - a[1]) for a, b in zip(main, main[1:]) if math.hypot(b[0] - a[0], b[1] - a[1]) > 1]
    hook = None
    if len(segments) >= 2:
        last, before = segments[-1], segments[-2]
        last_length = math.hypot(*last)
        if last_length < 0.3 * length and last_length < 170 and _turn(before, last) > 65:
            hook = _direction(*last)
            segments = segments[:-1]
    # The brush's entry and any short wobble are not turns: fold a segment shorter than an eighth
    # of the stroke (and under 110 units) into its neighbour.
    floor = min(110.0, length / 8)
    while len(segments) > 1 and math.hypot(*segments[0]) < floor:
        segments = [(segments[0][0] + segments[1][0], segments[0][1] + segments[1][1])] + segments[2:]
    kept: list[tuple[float, float]] = []
    for segment in segments:
        if kept and math.hypot(*segment) < floor:
            kept[-1] = (kept[-1][0] + segment[0], kept[-1][1] + segment[1])
        else:
            kept.append(segment)
    segments = kept
    # Merge consecutive segments that run the same way.
    words: list[str] = []
    for segment in segments:
        word = _direction(*segment)
        if not words or words[-1] != word:
            words.append(word)
    if length < 120 and not hook:
        kind = f"a dot, {words[0] if words else 'down'}"
    else:
        kind = ", then turning ".join(words) if words else "a dot"
        if hook:
            kind += f", ending in a hook {hook.replace('across to the right', 'to the right')}"
    first = math.hypot(*segments[0]) if segments else length
    return {"kind": kind, "length": length, "first": first, "turns": len(words) > 1,
            "start": points[0], "end": points[-1],
            "main": [words[0]] if words else [], "hook": hook, "points": points}


def region(x: float, y: float) -> str:
    column = "left" if x < BOX / 3 else "right" if x > 2 * BOX / 3 else "centre"
    row = "top" if y < BOX / 3 else "bottom" if y > 2 * BOX / 3 else "middle"
    return "centre" if (row, column) == ("middle", "centre") else f"{row} {column}" if column != "centre" else f"{row} centre"


def _bbox_of_outline(outline: str) -> tuple[float, float, float, float]:
    import re

    numbers = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", outline)]
    xs, ys = numbers[0::2], numbers[1::2]
    left, right = min(xs), max(xs)
    top, bottom = TOP - max(ys), TOP - min(ys)
    return left, top, right, bottom


def masks(outlines: list[str]) -> list[np.ndarray]:
    """Each stroke rendered alone, 256 px, as a boolean mask in the viewer's square."""
    import resvg_py
    from PIL import Image

    size = BOX // SCALE
    found = []
    for outline in outlines:
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {BOX} {BOX}" width="{size}" '
               f'height="{size}"><rect width="{BOX}" height="{BOX}" fill="#fff"/>'
               f'<g transform="translate(0 {TOP}) scale(1 -1)"><path d="{outline}" fill="#000"/></g></svg>')
        data = bytes(resvg_py.svg_to_bytes(svg_string=svg, width=size, height=size))
        pixels = np.asarray(Image.open(io.BytesIO(data)).convert("L"))
        found.append(pixels < 128)
    return found


def _disc(center: tuple[float, float], radius: int) -> np.ndarray:
    size = BOX // SCALE
    yy, xx = np.mgrid[0:size, 0:size]
    cx, cy = center[0] / SCALE, center[1] / SCALE
    return (xx - cx) ** 2 + (yy - cy) ** 2 <= radius ** 2


def _param_near(shape: dict[str, Any], contact: np.ndarray) -> float:
    """Where along a stroke (0–1) the contact pixels' centre lies: the nearest point of its median."""
    ys, xs = np.nonzero(contact)
    if not len(xs):
        return 0.5
    cx, cy = float(xs.mean()) * SCALE, float(ys.mean()) * SCALE
    points = shape["points"]
    cumulative = [0.0]
    for a, b in zip(points, points[1:]):
        cumulative.append(cumulative[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    total = cumulative[-1] or 1.0
    best, where = float("inf"), 0.5
    for (a, b), start, stop in zip(zip(points, points[1:]), cumulative, cumulative[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        span = dx * dx + dy * dy or 1.0
        t = max(0.0, min(1.0, ((cx - a[0]) * dx + (cy - a[1]) * dy) / span))
        distance = math.hypot(a[0] + dx * t - cx, a[1] + dy * t - cy)
        if distance < best:
            best, where = distance, (start + (stop - start) * t) / total
    return where


def _part(t: float) -> str:
    return "start" if t < 0.2 else "end" if t > 0.8 else "middle"


def relations(shapes: list[dict[str, Any]], stroke_masks: list[np.ndarray]) -> list[str]:
    """Which strokes touch, cross or nearly touch, measured on the rendered strokes."""
    from scipy.ndimage import binary_dilation, distance_transform_edt

    grown = [binary_dilation(m, iterations=1) for m in stroke_masks]
    distances = [distance_transform_edt(~m) for m in stroke_masks]
    found = []
    for i in range(len(shapes)):
        for j in range(i + 1, len(shapes)):
            a, b = f"S{i + 1}", f"S{j + 1}"
            overlap = int((grown[i] & grown[j]).sum())
            if overlap >= 2:
                ends_b = [name for name, point in (("start", shapes[j]["start"]), ("end", shapes[j]["end"]))
                          if (grown[i] & _disc(point, END_RADIUS)).any()]
                ends_a = [name for name, point in (("start", shapes[i]["start"]), ("end", shapes[i]["end"]))
                          if (grown[j] & _disc(point, END_RADIUS)).any()]
                contact = grown[i] & grown[j]
                at_a = _part(_param_near(shapes[i], contact))
                at_b = _part(_param_near(shapes[j], contact))
                if not ends_a and not ends_b:
                    found.append(f"{a} and {b} cross (at the {at_a} of {a}, the {at_b} of {b})")
                elif ends_b and not ends_a:
                    found.append(f"{b}'s {' and '.join(ends_b)} touches {a} (at the {at_a} of {a})")
                elif ends_a and not ends_b:
                    found.append(f"{a}'s {' and '.join(ends_a)} touches {b} (at the {at_b} of {b})")
                else:
                    found.append(f"{a}'s {' and '.join(ends_a)} meets {b}'s {' and '.join(ends_b)}")
                continue
            if not stroke_masks[j].any():
                continue
            gap = float(distances[i][stroke_masks[j]].min())
            if gap <= (GAP_LIMIT if len(shapes) <= 8 else DENSE_GAP_LIMIT):
                near = (distances[i] <= gap + 1.5) & (distances[j] <= gap + 1.5)
                found.append(f"{a} and {b} do NOT touch: a small gap of about {gap * SCALE * 100 / BOX:.1f}% "
                             f"of the box, between the {_part(_param_near(shapes[i], near))} of {a} "
                             f"and the {_part(_param_near(shapes[j], near))} of {b}")
    return found



# ── components ─────────────────────────────────────────────────────────────


def parse_ids(text: str) -> Any:
    """An ideographic description sequence as a tree: (operator, [children]) or a character."""
    position = 0

    def node() -> Any:
        nonlocal position
        if position >= len(text):
            return "？"
        char = text[position]
        position += 1
        if char in IDS_ARITY:
            return (char, [node() for _ in range(IDS_ARITY[char])])
        return char

    return node()


def component_at(tree: Any, path: list[int]) -> Any:
    for index in path:
        if isinstance(tree, tuple) and index < len(tree[1]):
            tree = tree[1][index]
        else:
            return "？"
    return tree


def _label(tree: Any) -> str:
    if isinstance(tree, tuple):
        return tree[0] + "".join(_label(child) for child in tree[1])
    return tree


# ── the sheet ──────────────────────────────────────────────────────────────


def _pct(value: float) -> int:
    return round(value * 100 / BOX)


def _nested(name: str, members: list[int], boxes: list[tuple[float, float, float, float]],
            lookup: dict[str, dict[str, Any]], scripts: dict[str, dict[str, Any]], indent: str,
            depth: int = 0) -> list[str]:
    """A component's own parts, from its own entry: its strokes keep their order inside a compound."""
    entry = lookup.get(name) or {}
    tree = parse_ids(entry.get("decomposition") or "？")
    matches = entry.get("matches") or []
    if depth > 1 or not isinstance(tree, tuple) or len(matches) != len(members) or len(members) < 3:
        return []
    groups: dict[int, list[int]] = {}
    for own, path in zip(members, matches):
        if path:
            groups.setdefault(path[0], []).append(own)
    if len(groups) < 2:
        return []
    found = []
    for index, inner in groups.items():
        part = _label(component_at(tree, [index]))
        left = min(boxes[i][0] for i in inner); top = min(boxes[i][1] for i in inner)
        right = max(boxes[i][2] for i in inner); bottom = max(boxes[i][3] for i in inner)
        full = SIDE_FORMS.get(part)
        known = " (scripted)" if part in scripts or (full in scripts if full else False) else ""
        found.append(f"{indent}- inside {name}: **{part}**{f' (side form of {full})' if full else ''}{known}: "
                     f"{' '.join(f'S{i + 1}' for i in inner)}; box x {_pct(left)}–{_pct(right)}%, "
                     f"y {_pct(top)}–{_pct(bottom)}%")
        found += _nested(part, inner, boxes, lookup, scripts, indent + "  ", depth + 1)
    return found


def sheet(character: str, entry: dict[str, Any], data: dict[str, Any], item: dict[str, Any],
          scripts: dict[str, dict[str, Any]], counterpart: str | None,
          lookup: dict[str, dict[str, Any]] | None = None) -> str:
    """The fact sheet for one character, in markdown, for the script writer."""
    outlines, medians = data["strokes"], data["medians"]
    shapes = [stroke_shape(m) for m in medians]
    stroke_masks = masks(outlines)
    boxes = [_bbox_of_outline(o) for o in outlines]
    etymology = entry.get("etymology") or {}
    lines = [f"# {character}", ""]
    lines.append(f"- Definition: {entry.get('definition') or '—'}; pinyin {', '.join(entry.get('pinyin') or []) or '—'}")
    lines.append(f"- Source: {etymology.get('type')} — “{(etymology.get('hint') or '').strip()}”")
    ranks = item.get("ranks") or {}
    used = ", ".join(f"{name} #{rank + 1}" for name, rank in (("Simplified Chinese", ranks.get("zh")),
                     ("Traditional Chinese", ranks.get("zhHant")), ("Japanese", ranks.get("ja")))
                     if rank is not None)
    lines.append(f"- How common: {used or 'rare in all three'} (group {item.get('group')})")
    if counterpart:
        lines.append(f"- {counterpart}")
    lines.append(f"- {len(outlines)} strokes")

    tree = parse_ids(entry.get("decomposition") or "？")
    matches = entry.get("matches") or []
    if isinstance(tree, tuple):
        lines += ["", f"## Components: {_label(tree)} ({IDS_NAMES.get(tree[0], tree[0])})", ""]
        groups: dict[str, list[int]] = {}
        for index, path in enumerate(matches):
            key = "unmatched" if path is None else ".".join(map(str, path[:1])) if path else "whole"
            groups.setdefault(key, []).append(index)
        for key, members in groups.items():
            if key in ("unmatched", "whole"):
                name = "(not matched to a component)" if key == "unmatched" else character
            else:
                name = _label(component_at(tree, [int(key)]))
            left = min(boxes[i][0] for i in members); top = min(boxes[i][1] for i in members)
            right = max(boxes[i][2] for i in members); bottom = max(boxes[i][3] for i in members)
            full = SIDE_FORMS.get(name)
            lines.append(f"- **{name}**{f' (side form of {full})' if full else ''}: "
                         f"{' '.join(f'S{i + 1}' for i in members)}; box x {_pct(left)}–{_pct(right)}%, "
                         f"y {_pct(top)}–{_pct(bottom)}% (width {_pct(right - left)}%, height {_pct(bottom - top)}%)")
            subtree = component_at(tree, [int(key)]) if key not in ("unmatched", "whole") else None
            if isinstance(subtree, tuple):
                # A group of components, split by the compound's own deeper matches.
                inner: dict[int, list[int]] = {}
                for i in members:
                    path = matches[i] or []
                    if len(path) > 1:
                        inner.setdefault(path[1], []).append(i)
                for index, strokes_in in inner.items():
                    part = _label(component_at(subtree, [index]))
                    left = min(boxes[i][0] for i in strokes_in); top = min(boxes[i][1] for i in strokes_in)
                    right = max(boxes[i][2] for i in strokes_in); bottom = max(boxes[i][3] for i in strokes_in)
                    known = " (scripted)" if part in scripts else ""
                    lines.append(f"  - inside: **{part}**{known}: {' '.join(f'S{i + 1}' for i in strokes_in)}; "
                                 f"box x {_pct(left)}–{_pct(right)}%, y {_pct(top)}–{_pct(bottom)}%")
            elif lookup and name not in scripts:
                lines += _nested(name, members, boxes, lookup, scripts, "  ")
            reuse = scripts.get(name) or (scripts.get(full) if full and len(full) == 1 else None)
            if reuse:
                lines.append(f"  - already scripted ({name if name in scripts else full}): object “{reuse['object'].strip()}”")
                for line in reuse.get("strokes") or []:
                    lines.append(f"    - {line['where'].strip()}: {line['part'].strip()}")
    elif isinstance(tree, str) and tree not in ("？", character):
        lines += ["", f"## Component: {tree}"]

    lines += ["", "## Strokes, in writing order (numbers are for you only; never write them in a script)", ""]
    for index, (shape, box) in enumerate(zip(shapes, boxes)):
        start, end = shape["start"], shape["end"]
        lines.append(f"- **S{index + 1}** {shape['kind']}; from {region(*start)} ({_pct(start[0])}, {_pct(start[1])}) "
                     f"to {region(*end)} ({_pct(end[0])}, {_pct(end[1])}); length {_pct(shape['length'])}% of the box; "
                     f"spans x {_pct(box[0])}–{_pct(box[2])}%, y {_pct(box[1])}–{_pct(box[3])}%")

    found = relations(shapes, stroke_masks)
    lines += ["", "## Touches, crossings and gaps (measured on the rendered strokes)", ""]
    lines += [f"- {line}" for line in found] or ["- no stroke touches another"]
    touched = {int(n) - 1 for line in found if "NOT" not in line for n in __import__("re").findall(r"S(\d+)", line)}
    alone = [f"S{i + 1}" for i in range(len(shapes)) if i not in touched]
    if alone and len(shapes) > 1:
        lines.append(f"- stands free of every other stroke: {' '.join(alone)}")

    # Lengths of strokes running the same main way, longest first, as ratios to the longest.
    lines += ["", "## Lengths of strokes running the same way", ""]
    by_way: dict[str, list[int]] = {}
    for index, shape in enumerate(shapes):
        if shape["main"] and "dot" not in shape["kind"]:
            way = "across" if shape["main"][0].startswith("across") else shape["main"][0]
            by_way.setdefault(way, []).append(index)
    any_listed = False
    for way, members in by_way.items():
        if len(members) < 2:
            continue
        any_listed = True
        # A stroke that turns is compared by its first leg, the part running this way.
        size = {i: shapes[i]["first"] if shapes[i]["turns"] else shapes[i]["length"] for i in members}
        longest = max(size.values()) or 1.0
        listed = ", ".join(f"S{i + 1} {size[i] / longest:.2f}{' (its first leg, before it turns)' if shapes[i]['turns'] else ''}"
                           for i in members)
        lines.append(f"- {way}: {listed} (1.00 is the longest)")
    if not any_listed:
        lines.append("- no two strokes run the same way")
    return "\n".join(lines) + "\n"


def numbered_sheet(data: dict[str, Any]) -> bytes:
    """A coloured, numbered drawing of the strokes for the writer's eyes only, never for a model."""
    import resvg_py

    colours = ("#e53935", "#1e6fd9", "#2e9e44", "#f28c00", "#8e24aa", "#00acc1", "#e91e8c",
               "#7b4a2a", "#c9a400", "#6a9a2a", "#1a237e", "#8a8a8a")
    paths = "".join(f'<path d="{o}" fill="{colours[i % len(colours)]}" fill-opacity="0.85"/>'
                    for i, o in enumerate(data["strokes"]))
    labels = ""
    for i, median in enumerate(data["medians"]):
        x, y = view(median[0])
        labels += (f'<circle cx="{x}" cy="{y}" r="26" fill="#fff" stroke="{colours[i % len(colours)]}" stroke-width="5"/>'
                   f'<text x="{x}" y="{y + 12}" font-size="34" font-family="Helvetica" text-anchor="middle" '
                   f'fill="#000">{i + 1}</text>')
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {BOX} {BOX}" width="512" height="512">'
           f'<rect width="{BOX}" height="{BOX}" fill="#fff"/>'
           + "".join(f'<line x1="{k}" y1="0" x2="{k}" y2="{BOX}" stroke="#ddd" stroke-width="2"/>'
                     f'<line x1="0" y1="{k}" x2="{BOX}" y2="{k}" stroke="#ddd" stroke-width="2"/>'
                     for k in (BOX // 4, BOX // 2, 3 * BOX // 4))
           + f'<g transform="translate(0 {TOP}) scale(1 -1)">{paths}</g>{labels}</svg>')
    return bytes(resvg_py.svg_to_bytes(svg_string=svg, width=512, height=512))

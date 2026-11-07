"""Build the meaning-space map from an Acervo export bundle.

One command from bundle to the prototype's fixture: read every word, embed every sense, lay each
language out in two dimensions, find regions on the layout, label them two ways without a model,
trace density contours, and write the result as the JavaScript the prototype loads.

    .venv/bin/python build.py --bundle path/to/acervo-all.zip --pictures --sample

The full map goes to `design/ui-prototype/map-data.local.js`, which is git-ignored: it is the
owner's whole vocabulary. `--sample` also writes `map-data.js`, a sparse copy of about 150 senses
per language, which is committed so a clean checkout still has a map to open.

`--compare MODEL` embeds with a second encoder as well and prints the measurements for both. The
layout is always drawn from `--model`.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import random
import re
import time
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
PROTOTYPE = ROOT / "design" / "ui-prototype"
OUT = HERE / "out"

DEFAULT_MODEL = "intfloat/multilingual-e5-small"
SEED = 42
# Below this a vocabulary's regions churn from one layout to the next (see the design), so a small
# language gets words and no regions.
MIN_FOR_REGIONS = 150
REGIONS, HOODS = 8, 30
# UMAP's two knobs. A small `min_dist` lets related senses clump, which is what turns one even disc
# into islands with sea between them; set by looking at the map, see the README.
NEIGHBOURS, MIN_DIST = 12, 0.1
# Density iso-levels as fractions of the peak. The first is the coast: high enough that sparse sea
# between clumps stays sea, so the vocabulary reads as islands rather than one continent.
CONTOUR_LEVELS = [0.16, 0.34, 0.56, 0.8]
SIDE = 1000.0


# ── reading ─────────────────────────────────────────────────────────────


@dataclass
class Sense:
    lang: str
    slug: str
    headword: str
    pos: str
    order: int
    of: int
    definition: str
    emoji: str
    domain: str
    gloss: str
    gloss_all: str
    text: str
    topics: list[str]
    lexeme: str
    picture: str | None = None
    vector: np.ndarray | None = field(default=None, repr=False)

    @property
    def id(self) -> str:
        return hashlib.sha1(f"{self.lang}\n{self.slug}\n{self.order}".encode()).hexdigest()[:15]


def read_bundles(paths: list[Path]) -> tuple[dict[str, dict], dict[tuple[str, str], dict], dict[str, zipfile.ZipFile]]:
    """Every vocabulary and every word across the bundles; a later bundle's copy of a word wins."""
    vocabularies: dict[str, dict] = {}
    words: dict[tuple[str, str], dict] = {}
    media: dict[str, zipfile.ZipFile] = {}
    for path in paths:
        bundle = zipfile.ZipFile(path)
        for name in bundle.namelist():
            if name == "vocabularies.yaml":
                for one in yaml.safe_load(bundle.read(name)) or []:
                    vocabularies[one["language"]] = one
                continue
            if name.startswith("media/"):
                media[name] = bundle
                continue
            match = re.match(r"^([A-Za-z-]+)/([^/]+)\.yaml$", name)
            if not match:
                continue
            word = yaml.safe_load(bundle.read(name))
            if not isinstance(word, dict) or word.get("status") == "aside":
                continue
            words[(match.group(1), match.group(2))] = word
    return vocabularies, words, media


def senses_of(vocabularies: dict[str, dict], words: dict[tuple[str, str], dict]) -> list[Sense]:
    """Every sense. A word whose senses say exactly what an earlier word's do is left out: the
    19 Sep 2026 export carried 227 English words twice (`burgeon.yaml`, `burgeon-2.yaml`), and two
    identical points draw as one point with its label written over itself."""
    out: list[Sense] = []
    seen: set[tuple] = set()
    duplicates = Counter()
    for (lang, slug), word in sorted(words.items()):
        vocabulary = vocabularies.get(lang, {})
        first = (vocabulary.get("glossLangs") or [None])[0]
        senses = sorted(word.get("senses") or [], key=lambda s: s.get("order", 0))
        identity = (lang, word.get("headword"), tuple((s.get("definition") or "").strip() for s in senses))
        if identity in seen:
            duplicates[lang] += 1
            continue
        seen.add(identity)
        for index, sense in enumerate(senses):
            glosses = sense.get("glosses") or []
            terms = [t for g in glosses for t in (g.get("terms") or [])]
            preferred = next((g for g in glosses if g.get("lang") == first), glosses[0] if glosses else None)
            preferred_terms = (preferred or {}).get("terms") or []
            definition = (sense.get("definition") or "").strip()
            headword = str(word.get("headword") or slug)
            pos = str(word.get("pos") or "")
            out.append(Sense(
                lang=lang, slug=slug, headword=headword, pos=pos, order=index, of=len(senses),
                definition=definition,
                emoji=str(sense.get("emoji") or word.get("emoji") or ""),
                domain=str(sense.get("domain") or ""),
                gloss=str(preferred_terms[0]) if preferred_terms else "",
                gloss_all="; ".join(str(t) for t in preferred_terms),
                # The design's template, shared with the discovery experiment so both compute the
                # same vectors.
                text=f"{headword} ({pos}) — {definition} — {'; '.join(str(t) for t in terms)}",
                topics=[str(t) for t in word.get("topics") or []],
                lexeme=f"{lang}/{slug}",
            ))
    if duplicates:
        print("left out as exact duplicates: " + ", ".join(f"{k} {v}" for k, v in sorted(duplicates.items())))
    return out


# ── embedding, cached by what is embedded ───────────────────────────────


def digest(model: str, text: str) -> str:
    return hashlib.sha256(f"{model}\n{text}".encode()).hexdigest()


def embed(senses: list[Sense], model_name: str) -> tuple[np.ndarray, float]:
    """Unit vectors for every sense. Only texts the cache has not seen are encoded."""
    cache_path = OUT / "cache" / (re.sub(r"[^A-Za-z0-9]+", "-", model_name) + ".npz")
    cache: dict[str, np.ndarray] = {}
    if cache_path.exists():
        stored = np.load(cache_path, allow_pickle=False)
        cache = dict(zip(stored["keys"].tolist(), stored["vectors"]))
    keys = [digest(model_name, s.text) for s in senses]
    missing = sorted({k: s.text for k, s in zip(keys, senses) if k not in cache}.items())
    seconds = 0.0
    if missing:
        from sentence_transformers import SentenceTransformer

        encoder = SentenceTransformer(model_name, device="cpu")
        # e5 is trained with a role prefix; "query: " is its advice for symmetric tasks like this.
        prefix = "query: " if "e5" in model_name else ""
        started = time.perf_counter()
        vectors = encoder.encode([prefix + text for _, text in missing], batch_size=64,
                                 normalize_embeddings=True, show_progress_bar=False)
        seconds = time.perf_counter() - started
        for (key, _), vector in zip(missing, vectors):
            cache[key] = vector.astype(np.float32)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        np.savez(cache_path, keys=np.array(list(cache.keys())), vectors=np.stack(list(cache.values())))
        print(f"  embedded {len(missing)} new texts with {model_name} in {seconds:.1f}s")
    matrix = np.stack([cache[k] for k in keys]).astype(np.float32)
    matrix /= np.linalg.norm(matrix, axis=1, keepdims=True)
    return matrix, seconds


# ── layout, regions, labels ─────────────────────────────────────────────


def layout(vectors: np.ndarray) -> np.ndarray:
    import umap

    reducer = umap.UMAP(n_neighbors=NEIGHBOURS, min_dist=MIN_DIST, metric="cosine", random_state=SEED)
    return reducer.fit_transform(vectors)


def normalise(coords: np.ndarray) -> np.ndarray:
    """Into a SIDE × SIDE square, centred, aspect kept."""
    low, high = coords.min(axis=0), coords.max(axis=0)
    scale = SIDE / max(float((high - low).max()), 1e-9)
    centred = (coords - (low + high) / 2) * scale + SIDE / 2
    return centred


def procrustes(moving: np.ndarray, fixed: np.ndarray) -> np.ndarray:
    """`moving` rotated, reflected, scaled and shifted onto `fixed` as closely as possible."""
    mu_m, mu_f = moving.mean(axis=0), fixed.mean(axis=0)
    a, b = moving - mu_m, fixed - mu_f
    u, s, vt = np.linalg.svd(a.T @ b)
    rotation = u @ vt
    scale = s.sum() / (a ** 2).sum()
    return a @ rotation * scale + mu_f


def regions(coords: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Two nested cuts of one Ward tree over the layout: a label has to sit over its points."""
    from scipy.cluster.hierarchy import fcluster, linkage

    tree = linkage(coords, method="ward")
    return fcluster(tree, REGIONS, criterion="maxclust") - 1, fcluster(tree, HOODS, criterion="maxclust") - 1


STOP = {
    "es": set("""dicho dicha indica indicar sirve ninguna ninguno vez tal poca poco usar sirve suele
        a al algo alguien alguna algunas alguno algunos ante antes aquel aquella así aun aunque bajo bien
        cada casi como con contra cosa cosas cual cuales cuando de del desde donde dos durante e el ella ellas
        ellos en entre era es esa esas ese eso esos esta estas este esto estos etc forma fue ha hace hacer hacia
        hasta la las le les lo los mas más me menos mismo mucho muy más ni no nos o otra otras otro otros para
        pero persona personas poco por porque que qué quien quién se ser si sin sino sobre su sus también tan
        tanto te tener tiene todo todos tu un una uno unos usa usado usada utiliza ya y alguna manera modo acción
        efecto relativo relativa perteneciente algo situación hecho estar decir dar tipo parte cierto cierta
        propio propia general especialmente generalmente suele frecuencia expresión indicar""".split()),
    "en": set("""a about above after again against all also an and any are as at be been being below between both
        but by can could did do does doing done down during each especially etc few for from further had has have
        having he her here hers him his how i if in into is it its itself just kind like made make makes may me
        more most much must my no nor not of off often on once one ones only or other our out over own person
        people same she should so some someone something such than that the their them then there these they
        thing things this those through to too under until up upon used using usually very was way we were
        what when where which while who whom why will with without would you your act state quality manner
        particular especially typically often showing shows shown extremely rather because able never
        someone's somebody""".split()),
}


def tokens(text: str, lang: str) -> list[str]:
    stop = STOP.get(lang, set())
    return [t for t in re.findall(r"[^\W\d_]{3,}", text.lower()) if t not in stop]


def ctfidf_terms(senses: list[Sense], labels: np.ndarray, lang: str, top: int = 3) -> dict[int, list[str]]:
    """c-TF-IDF: each cluster's definitions as one document, terms scored against every cluster."""
    counts: dict[int, Counter] = defaultdict(Counter)
    for sense, label in zip(senses, labels):
        counts[int(label)].update(tokens(sense.definition, lang))
    total = Counter()
    for c in counts.values():
        total.update(c)
    average = sum(sum(c.values()) for c in counts.values()) / max(len(counts), 1)
    out: dict[int, list[str]] = {}
    for label, c in counts.items():
        size = sum(c.values()) or 1
        scored = sorted(c, key=lambda t: -(c[t] / size) * math.log(1 + average / total[t]))
        out[label] = [t for t in scored if c[t] > 1][:top] or scored[:top]
    return out


def nearest_words(senses: list[Sense], vectors: np.ndarray, members: list[int], top: int = 3) -> list[str]:
    centre = vectors[members].mean(axis=0)
    order = sorted(members, key=lambda i: -float(vectors[i] @ centre))
    words: list[str] = []
    for i in order:
        if senses[i].headword not in words:
            words.append(senses[i].headword)
        if len(words) == top:
            break
    return words


def ranks(vectors: np.ndarray, hoods: np.ndarray | None) -> np.ndarray:
    """How central each sense is to its neighbourhood, 0–1: the order labels are allowed in."""
    if hoods is None:
        centre = vectors.mean(axis=0)
        sim = vectors @ centre
        return (sim - sim.min()) / max(float(sim.max() - sim.min()), 1e-9)
    out = np.zeros(len(vectors))
    for hood in np.unique(hoods):
        members = np.where(hoods == hood)[0]
        sim = vectors[members] @ vectors[members].mean(axis=0)
        order = np.argsort(np.argsort(-sim))
        out[members] = 1 - order / max(len(members) - 1, 1)
    return out


def neighbours(senses: list[Sense], vectors: np.ndarray, k: int) -> list[list[int]]:
    sim = vectors @ vectors.T
    out = []
    for i in range(len(senses)):
        order = np.argsort(-sim[i])
        out.append([int(j) for j in order if senses[j].lexeme != senses[i].lexeme][:k])
    return out


def contours(coords: np.ndarray) -> list[list]:
    """Density iso-lines in map coordinates, so the browser draws them with no library."""
    import contourpy
    from scipy.stats import gaussian_kde

    kde = gaussian_kde(coords.T, bw_method=0.055)
    pad = 60
    xs = np.linspace(-pad, SIDE + pad, 150)
    ys = np.linspace(-pad, SIDE + pad, 150)
    gx, gy = np.meshgrid(xs, ys)
    density = kde(np.vstack([gx.ravel(), gy.ravel()])).reshape(gx.shape)
    generator = contourpy.contour_generator(gx, gy, density)
    peak = float(density.max())
    out = []
    for level, fraction in enumerate(CONTOUR_LEVELS):
        for line in generator.lines(peak * fraction):
            if len(line) < 6:
                continue
            flat = [round(float(v), 1) for point in line[::2] for v in point]
            out.append([level, flat])
    return out


# ── measurements ────────────────────────────────────────────────────────


def topic_agreement(senses: list[Sense], vectors: np.ndarray, k: int = 10) -> tuple[float, float]:
    """How often a sense's k nearest (other words') senses share one of its word's topics, against
    the same rate for k senses drawn at random. The owner's topics are free labels."""
    rng = random.Random(SEED)
    tagged = [i for i, s in enumerate(senses) if s.topics]
    near = neighbours(senses, vectors, k)
    hit = base = n = 0
    for i in tagged:
        mine = set(senses[i].topics)
        hit += sum(1 for j in near[i] if mine & set(senses[j].topics))
        base += sum(1 for j in rng.sample(range(len(senses)), k) if mine & set(senses[j].topics))
        n += k
    return hit / max(n, 1), base / max(n, 1)


# ── one language ────────────────────────────────────────────────────────


def fingerprint(ids: list[tuple[str, list[str]]]) -> str:
    """Which senses each region holds. Model labels are keyed by region id, and a new layout
    renumbers regions, so labels written for another layout must not be merged."""
    return hashlib.sha1(json.dumps(sorted(ids)).encode()).hexdigest()[:16]


def build_language(lang: str, senses: list[Sense], vectors: np.ndarray, vocabulary: dict,
                   model_labels: dict | None, model: str) -> tuple[dict, dict]:
    started = time.perf_counter()
    coords = normalise(layout(vectors)) if len(senses) >= 5 else np.full((len(senses), 2), SIDE / 2)
    layout_seconds = time.perf_counter() - started
    big = len(senses) >= MIN_FOR_REGIONS
    region_of, hood_of = regions(coords) if big else (None, None)
    rank = ranks(vectors, hood_of)
    near = neighbours(senses, vectors, 30)
    definition_lang = vocabulary.get("definitionLang", lang)

    region_list = []
    if big:
        members_of = [(f"{lvl}{k}", sorted(s.id for s, lab in zip(senses, labels) if lab == k))
                      for lvl, labels, count in (("r", region_of, REGIONS), ("h", hood_of, HOODS))
                      for k in range(count)]
        if model_labels and model_labels.get("_fingerprint") != fingerprint(members_of):
            print(f"  {lang}: model labels were written for another layout; run label_model.py again")
            model_labels = None
        for level, labels, count in (("region", region_of, REGIONS), ("hood", hood_of, HOODS)):
            terms = ctfidf_terms(senses, labels, definition_lang)
            for index in range(count):
                members = [i for i in range(len(senses)) if labels[i] == index]
                if not members:
                    continue
                centre = coords[members].mean(axis=0)
                entry = {
                    "id": f"{level[0]}{index}", "level": level, "index": index,
                    "x": round(float(centre[0]), 1), "y": round(float(centre[1]), 1),
                    "count": len(members),
                    "labels": {"words": nearest_words(senses, vectors, members),
                               "terms": terms.get(index, [])},
                }
                if level == "hood":
                    entry["region"] = int(region_of[members[0]])
                model = (model_labels or {}).get(f"{level[0]}{index}")
                if model:
                    entry["labels"]["model"] = model
                region_list.append(entry)

    # The state "since you last opened it": the same language with a few words not yet added, laid
    # out with the same seed. Whole words go, since a word arrives with all of its senses.
    before = None
    stats: dict = {"layoutSeconds": round(layout_seconds, 1)}
    if big:
        rng = random.Random(SEED)
        lexemes = sorted({s.lexeme for s in senses})
        rng.shuffle(lexemes)
        removed: set[str] = set()
        for lexeme in lexemes:
            if sum(1 for s in senses if s.lexeme in removed) >= 0.02 * len(senses):
                break
            removed.add(lexeme)
        kept = [i for i, s in enumerate(senses) if s.lexeme not in removed]
        raw = normalise(layout(vectors[kept]))
        aligned = procrustes(raw, coords[kept])
        displacement_raw = np.linalg.norm(raw - coords[kept], axis=1)
        displacement = np.linalg.norm(aligned - coords[kept], axis=1)
        stats.update({
            "beforeRemovedSenses": len(senses) - len(kept),
            "medianShiftRaw": round(float(np.median(displacement_raw)), 1),
            "medianShiftAligned": round(float(np.median(displacement)), 1),
            "p90ShiftAligned": round(float(np.percentile(displacement, 90)), 1),
        })
        before = {"points": [[i, round(float(x), 1), round(float(y), 1)] for i, (x, y) in zip(kept, aligned)]}

    lexeme_senses: dict[str, list[int]] = defaultdict(list)
    for i, s in enumerate(senses):
        lexeme_senses[s.lexeme].append(i)
    points = []
    for i, s in enumerate(senses):
        points.append({
            "id": s.id, "w": s.lexeme, "headword": s.headword, "emoji": s.emoji, "pos": s.pos,
            "domain": s.domain, "gloss": s.gloss, "glossAll": s.gloss_all, "definition": s.definition,
            "order": s.order, "of": s.of,
            "x": round(float(coords[i][0]), 1), "y": round(float(coords[i][1]), 1),
            "r": int(region_of[i]) if big else -1, "h": int(hood_of[i]) if big else -1,
            "rank": round(float(rank[i]), 3),
            "nb": near[i][:5],
            "_near": near[i],
            **({"pic": s.picture} if s.picture else {}),
        })
    data = {
        "language": lang, "definitionLang": definition_lang,
        "name": vocabulary.get("displayName", lang), "flag": vocabulary.get("flag", ""),
        "model": model, "side": SIDE,
        "words": len(lexeme_senses), "senses": len(senses),
        "points": points, "regions": region_list,
        "contours": contours(coords) if big else [],
        **({"before": before} if before else {}),
    }
    return data, stats


# ── the committed sample ────────────────────────────────────────────────


def sample(data: dict, per_hood: int = 5) -> dict:
    """About 150 senses: the most central words of each neighbourhood, with every sense of each
    word, positioned where the full map put them. Labels are recomputed from what is kept, so no
    word outside the sample is named."""
    points = data["points"]
    if not data["regions"]:
        chosen_words = {p["w"] for p in points[:40]}
    else:
        chosen_words: set[str] = set()
        by_hood: dict[int, list[dict]] = defaultdict(list)
        for p in points:
            by_hood[p["h"]].append(p)
        for hood_points in by_hood.values():
            for p in sorted(hood_points, key=lambda p: -p["rank"]):
                if sum(1 for q in hood_points if q["w"] in chosen_words) >= per_hood:
                    break
                chosen_words.add(p["w"])
    keep = [i for i, p in enumerate(points) if p["w"] in chosen_words]
    index = {old: new for new, old in enumerate(keep)}
    kept = []
    for old in keep:
        p = {k: v for k, v in points[old].items() if k not in ("pic",)}
        p["nb"] = [index[j] for j in points[old]["_near"] if j in index][:5]
        kept.append(p)
    regions = []
    for region in data["regions"]:
        members = [p for p in kept if (p["r"] if region["level"] == "region" else p["h"]) == region["index"]]
        if not members:
            continue
        words = []
        for p in sorted(members, key=lambda p: -p["rank"]):
            if p["headword"] not in words:
                words.append(p["headword"])
        labels = {"words": words[:3], "terms": region["labels"]["terms"]}
        if "model" in region["labels"]:
            labels["model"] = region["labels"]["model"]
        regions.append({**region, "count": len(members), "labels": labels})
    before = None
    if data.get("before"):
        before = {"points": [[index[i], x, y] for i, x, y in data["before"]["points"] if i in index]}
    return {**data, "words": len({p["w"] for p in kept}), "senses": len(kept),
            "points": kept, "regions": regions, **({"before": before} if before else {})}


def strip_private(data: dict) -> dict:
    return {**data, "points": [{k: v for k, v in p.items() if not k.startswith("_")} for p in data["points"]]}


def write_js(path: Path, name: str, maps: dict[str, dict], note: str) -> None:
    body = json.dumps(maps, ensure_ascii=False, separators=(",", ":"))
    path.write_text(f"/* {note} */\nwindow.{name} = {body};\n", encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)} ({path.stat().st_size / 1024:.0f} KB)")


# ── pictures ────────────────────────────────────────────────────────────


def pictures(senses: list[Sense], media: dict[str, zipfile.ZipFile]) -> None:
    from PIL import Image

    target = PROTOTYPE / "map-local"
    count = 0
    for s in senses:
        name = f"media/{s.lang}/{s.slug}-{s.order + 1}.webp"
        if name not in media:
            continue
        out = target / s.lang / f"{s.slug}-{s.order + 1}.webp"
        if not out.exists():
            out.parent.mkdir(parents=True, exist_ok=True)
            image = Image.open(io.BytesIO(media[name].read(name)))
            image.thumbnail((360, 360))
            image.save(out, "WEBP", quality=72)
        s.picture = f"map-local/{s.lang}/{out.name}"
        count += 1
    print(f"  {count} pictures ready for the peek")


# ── main ────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--bundle", type=Path, action="append", required=True,
                        help="an Acervo export bundle; repeat for several, later ones win")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--compare", action="append", default=[], help="a second encoder to measure")
    parser.add_argument("--pictures", action="store_true", help="extract sense pictures for the peek")
    parser.add_argument("--sample", action="store_true", help="also write the committed sample")
    args = parser.parse_args(argv)

    vocabularies, words, media = read_bundles(args.bundle)
    senses = senses_of(vocabularies, words)
    by_lang: dict[str, list[Sense]] = defaultdict(list)
    for s in senses:
        by_lang[s.lang].append(s)
    print("senses: " + ", ".join(f"{lang} {len(v)}" for lang, v in sorted(by_lang.items())))
    if args.pictures:
        pictures(senses, media)

    maps: dict[str, dict] = {}
    report: dict[str, dict] = {}
    for lang, group in sorted(by_lang.items()):
        vectors, seconds = embed(group, args.model)
        model_labels_path = OUT / f"model-labels-{lang}.json"
        model_labels = json.loads(model_labels_path.read_text()) if model_labels_path.exists() else None
        data, stats = build_language(lang, group, vectors, vocabularies.get(lang, {}), model_labels,
                                     args.model)
        maps[lang] = data
        stats["embedSeconds"] = round(seconds, 1)
        if len(group) >= MIN_FOR_REGIONS:
            for model in [args.model, *args.compare]:
                v = vectors if model == args.model else embed(group, model)[0]
                agreement, chance = topic_agreement(group, v)
                stats[f"topicAgreement@10 {model}"] = round(agreement, 3)
                stats["topicAgreement@10 chance"] = round(chance, 3)
        # What the model-label script needs: each region's members, most central first.
        if data["regions"]:
            summary = []
            for region in data["regions"]:
                key = "r" if region["level"] == "region" else "h"
                members = sorted((p for p in data["points"]
                                  if (p["r"] if key == "r" else p["h"]) == region["index"]),
                                 key=lambda p: -p["rank"])
                summary.append({"id": region["id"], "level": region["level"],
                            "ids": sorted(p["id"] for p in data["points"]
                                          if (p["r"] if key == "r" else p["h"]) == region["index"]),
                                "region": region.get("region"),
                                "members": [f"{p['headword']} — {p['glossAll'] or p['definition']}"
                                            for p in members[:25]]})
            OUT.mkdir(exist_ok=True)
            (OUT / f"regions-{lang}.json").write_text(json.dumps(
                {"language": lang, "definitionLang": data["definitionLang"], "regions": summary},
                ensure_ascii=False, indent=1))
        report[lang] = stats
        print(f"{lang}: {json.dumps(stats, ensure_ascii=False)}")

    write_js(PROTOTYPE / "map-data.local.js", "MAP_LOCAL",
             {lang: strip_private(d) for lang, d in maps.items()},
             "The owner's whole vocabulary, laid out by experiments/meaning-space/build.py. Git-ignored.")
    if args.sample:
        write_js(PROTOTYPE / "map-data.js", "MAP_SAMPLE",
                 {lang: strip_private(sample(d)) for lang, d in maps.items()},
                 "A sparse sample of a real map, from experiments/meaning-space/build.py --sample.")
    OUT.mkdir(exist_ok=True)
    (OUT / "report.json").write_text(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()

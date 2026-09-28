# The meaning map · a vocabulary laid out by what it means

One language's senses on one map. Senses that mean related things sit together; zoomed out, the map
names its regions — the learner's interests, as their own words reveal them — and zoomed in it shows
the words and then what each means. Tapping a word peeks at it, and the peek opens the article.

The package is `src/acervo/meaning/`, drawn by `GET /map/{language}`; the look and the interaction are
the prototype's (`design/ui-prototype/README.md`, "The map"); the measurements are
[`experiments/meaning-space/`](../../experiments/meaning-space/README.md). What the map might become
— ghosts, other layers — is [`../plans/word-discovery.md`](../plans/word-discovery.md).

---

## One map per language, one point per sense

A learner's languages serve different purposes — one for travel, one for work, one for everyday life —
so the words held in each are a different set of interests. Pooled into one space they would make
regions that describe no single language's vocabulary. The map follows the language switcher, as
loops and stories do.

**A point is a sense, not a word**, because polysemy is exactly what a word-level map collapses. A
word with two meanings appears in two places, and selecting one draws faint arcs to the word's other
senses — the one thing a map of senses can show that a list cannot: where else the word lives.

## The embedding

Each sense is embedded from the text

```
{headword} ({pos}) — {definition} — {gloss terms}
```

and not from the bare surface form, whose embedding is dominated by spelling and frequency. It is the
template the discovery experiment (`interest-aligned-vocabulary-recommendation`) uses, so the two
compute the same vectors and that experiment can take them from Acervo.

**The encoder is `intfloat/multilingual-e5-small`**: 118 M parameters, 384 dimensions, MIT licensed,
pinned in `models/encoder.json`, baked into the image and loaded offline on the first map anyone asks
for — about half a gigabyte of the NAS's memory. It must be multilingual even with one map per
language, because every embedded text mixes two: a Spanish sense has a Spanish definition and English
glosses.

Measured on the real vocabulary as **topic agreement @10** — how often a sense's ten nearest senses of
other words share one of its word's topics, the owner's topics being free labels:

| | Spanish | English |
|---|---|---|
| `multilingual-e5-small` | 0.430 | 0.473 |
| `paraphrase-multilingual-MiniLM-L12-v2` | 0.443 | 0.490 |
| random neighbours | 0.182 | 0.244 |

Both encoders are more than twice chance and within two points of each other; this metric does not
separate them. A stronger encoder (bge-m3, EmbeddingGemma) waits for a sharper measure — the
discovery experiment's held-out recall. The model id is part of the cache key, so trying one is a
setting and a recompute.

**Computed on the server, not the device**: a phone pays for it in latency and battery, the server is
idle most of the time, and every device then reads the same answer.

**Embeddings live in a content-addressed cache beside the database**, `maps/embeddings/<model>/`, one
`.npy` per sense text **named by the digest of the model and the text** — the take store's pattern. The
alternatives each cost more:

| Option | Why not |
|---|---|
| A replicated collection | Megabytes of floats no device needs, a local schema bump, and a model change rewriting every row's revision |
| Columns on `senses` | A derived value in an authored record, and a changed replicated shape |
| A server-only table | A schema change, and lost on every rebuilt database |

The cache has no table, no schema and no converter, and survives rebuilds and re-imports because it
is keyed on text rather than on ids an import re-mints. **Invalidation is the digest**: a sense whose
text changes gets a new key and only it is embedded again; a new picture or example costs nothing.

## The layout

UMAP, cosine metric, 12 neighbours, **`min_dist` 0.1**, fixed seed. `min_dist` decides whether there is
a map at all: at 0.35 the senses spread into one even disc and the density contours are noise; at 0.1
related senses clump, and with the coast drawn at 16% of peak density the vocabulary reads as land
with inlets and islands.

**Clumping costs stability, and a fixed seed does not buy it back.** Removing 2% of the English words
and laying the map out again with the same seed returned it *mirrored* — a median point moved half
the map's width — which UMAP is free to do. So each new layout is:

1. **started from the previous one** — every sense the last map held begins where it was, and a new
   one begins beside its three nearest held senses;
2. then **aligned onto the previous one** — a Procrustes fit (rotation, reflection, scale and shift,
   one SVD) — before it is stored.

Median movement of a point, on a map 1,000 units across:

| | cold start | warm start + alignment |
|---|---|---|
| One edited Spanish sense | 140 | 37 |
| 2% more words | 179 | 39 |

Nothing is pinned: a sense still goes where its meaning now puts it. The map is meant to move as
little as it can, not to stay put.

## Regions and their names

**Regions are Ward clustering on the 2-D layout**, cut at two levels — about 8 regions and about 30
neighbourhoods — with no noise class.

- **On the layout rather than the vectors**, because a label has to sit over its points: a cluster
  found in 384 dimensions can land in pieces across the plane, and its label then describes a place
  where half of it is not.
- **Not HDBSCAN**, because it marks much of a thousand-word vocabulary as noise, and that noise is the
  long tail of minor interests worth keeping.
- **No regions below about 150 senses**: below that they churn from one layout to the next, so such a
  map (Chinese, today) shows only words.

**Names are model-written.** On the real vocabulary the model's names read as places — *dinero y
trabajo*, *pagos y deudas*, *aggression and hostility* — where the deterministic candidates did not:
the nearest headwords read as a list, and c-TF-IDF terms over the definitions carried boilerplate such
as *dicho* and *showing*. Names are written in the vocabulary's `definitionLang`.

The model is kept off the path that draws the map. A freshly drawn map queues one **`map.name` job**,
which names every region and neighbourhood in one call on the owner's text chain
(`prompts/acervo_map_names.md`); a second drawing before it lands queues nothing new, and a job whose
map has since been redrawn finds its fingerprint stale and does nothing. Until it lands a region shows
its most central words, and the map never waits for a name. The owner's standing rules are not
appended to this prompt, since it only labels.

## The artifact

The server keeps one drawn map per owner and language, `maps/artifacts/<owner>/<language>.json`:
`{fingerprint, model, side, words, senses, names, points, regions, contours}`.

- A point is `{sense, lexeme, x, y, r, h, rank, nb}` — the ids, the position, its region and
  neighbourhood, how central it is to its neighbourhood, and its five nearest senses of other words.
- A region is `{id, level, index, x, y, count, region?, labels: {words, terms, name?}}`.
- `names` is `pending` until the naming job lands, then `ready` — or `none` for a map with no regions,
  or a naming that failed for good.

**It carries no vectors and no text.** The device joins the ids to its replica, so an edited headword
shows at once and a map already drawn reads offline.

**The fingerprint** is a digest of every `(senseId, text digest)` pair, the model and the layout's
parameters. **The version** is the fingerprint and the state of the names together, because naming
changes the map without changing its layout: asked by fingerprint alone, a device holding the unnamed
map would be told it was current and never see the names. A device sends its version as `?have=`, and
a current map answers `{"current": true}` and nothing else.

## Drawn on request, not by a job

A map is redrawn when its fingerprint has changed, under one lock per owner and language, in the
request's thread pool. It is seconds of local CPU with no model call, and the one-at-a-time job runner
would leave it an hour behind an import. The one cold cost is the first embedding of a language: on a
laptop, 1,443 Spanish senses took 35 s cold and 3.4 s warm; the NAS is several times slower. It is paid
once, behind *Drawing your map*.

## On the device

The last map per language is kept in `mapStore.ts`, an IndexedDB store separate from the replica, so
neither wipe touches the other and the map opens at once and offline. The current one then arrives,
new points fade in and moved ones glide to their places — the map visibly grows by the words added
since it was last opened. With no stored map and no server it says so, and never shows a spinner that
cannot finish.

**The surface.** It is entered from the rail and, on a phone, the foot bar, and it replaces the list.
On the map the top bar carries the map's own row — Back, the name, the counts, Find, its own language
switcher — drawn by `MapView` through a portal into the bar's slot, so it is the top bar and not a card
over the map. ⌘ + scroll and ⌘= / ⌘− / ⌘0 zoom it — taking over the browser's page zoom while the map
is open, which works in the macOS host only because it binds no View ▸ Zoom item; adding one would
silently take those keys from the map. Each sense of an article has a button that opens the
map flown to that sense; *Open the article* from a peek lands on the peeked sense; Back returns either
way. The look is an atlas: a paper ground, region names in spaced Literata italic, words in Plex Sans,
faint density contours, and teal kept for the selection.

**Built so it can move out.** `web/src/meaningMap/` imports nothing of Acervo's (`boundary.test.ts`)
and takes its own `MapData`; `selectors.ts`'s adapter joins the artifact to the replica. On the server
`src/acervo/meaning/` stands alone like `images/`, with `services/meaning.py` as the binding layer and
`admin map export` giving texts and vectors to the discovery experiment (`admin map show` prints a
language's map as last drawn). Either half can move to the
discovery repository and come back as a package.

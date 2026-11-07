# Image benchmark guide

This is research tooling. It never changes the configured Anki image provider
or media cache.

## Install and inspect

```bash
uv sync
uv run python --version
uv run python -m experiments.image_benchmark.benchmark_image_models list
```

The repository pins Python 3.12 in `.python-version` and constrains the uv
project to `>=3.12,<3.13`. Use `uv run` for benchmark commands so a newer
Homebrew `python` cannot accidentally select an incompatible environment.

Only `icon_scene` is enabled by default because it has no model download or
network call. Every heavyweight and remote candidate must be named explicitly.

## Offline smoke path

```bash
uv run python -m experiments.image_benchmark.benchmark_image_models run \
  --stage smoke \
  --models icon_scene

uv run python -m experiments.image_benchmark.benchmark_image_models render-review --stage smoke
```

Open `output/image-benchmark/smoke/review.html`. The self-contained gallery
stores in-progress ratings in browser local storage and downloads portable
JSON. Identities remain blind until **Reveal model identities** is used.
Checkbox flags such as `irrelevant` and `unwanted-text` can be clicked directly;
flag changes are stored immediately alongside scores and rejection state.

Aggregate one or more downloaded ratings exports into a standalone interactive
report:

```bash
uv run python -m experiments.image_benchmark.benchmark_image_models aggregate-ratings \
  ~/Downloads/image-benchmark-smoke-ratings.json
```

By default this writes HTML and machine-readable JSON under
`output/image-benchmark/ratings/`. The HTML shows rejected-as-zero, accepted-only,
and raw weighted scores. Accepted-only metric averages exclude rejected images
while the rejection count and rate remain visible. It permits changing metric
weights, sorting by composite or individual metrics, and filtering to local
models. It initially shows all candidates and overlays mean/max runtime, peak
process RSS, backend-native accelerator memory when available, and configured
marginal cost. Default weights are mnemonic relevance 45%, visual appeal 30%,
artifact freedom 20%, and small-size legibility 5%.

Historical local runs have wall time and `/usr/bin/time -l` process RSS. That
RSS is useful but can understate pressure from PyTorch MPS and Apple's unified
GPU memory. New runs additionally record MLX peak allocated memory or PyTorch
MPS post-generation driver allocation in `runner.resource_usage`; these are
labelled separately rather than mixed with process RSS. Hosted client-process
memory is hidden because it says nothing about provider-side resource use.

Repeated runs for the same candidate/prompt/style/seed are averaged within that
evaluation cell before candidate means are calculated. This prevents stale or
repeated jobs from giving one model extra weight. Re-rendering the review gallery
keeps only the newest successful manifest for each evaluation cell, including
when operational configuration changes produced a new deterministic job ID.

For the next comparison, `finalist_efficient` uses all twelve terms with one
art-directed mnemonic style and seed 17: twelve jobs per candidate instead of
the full finalist stage's forty-eight. It now selects eight finalists by
default, including Gemini Pro Image. Run all 96 jobs with one resumable command:

```bash
uv run python -m experiments.image_benchmark.benchmark_image_models resume \
  --stage finalist_efficient \
  --execute-remote \
  --max-cost-usd 2.85
```

The configured remote projection is $2.818644: $1.608 for Gemini Pro Image,
$0.804 for Gemini Flash Image, $0.4032 for Flash Lite Image, and $0.003444 for
Cloudflare. The four local candidates have no marginal API cost. The harness
runs jobs sequentially, and `resume` skips completed outputs if the run is
interrupted.

To keep local system pressure attributable, the same eight finalists can still
be run one at a time:

```bash
uv run python -m experiments.image_benchmark.benchmark_image_models resume --stage finalist_efficient --models lcm_dreamshaper
uv run python -m experiments.image_benchmark.benchmark_image_models resume --stage finalist_efficient --models mflux_flux2_klein_q4
uv run python -m experiments.image_benchmark.benchmark_image_models resume --stage finalist_efficient --models sana_sprint_06b
uv run python -m experiments.image_benchmark.benchmark_image_models resume --stage finalist_efficient --models drawthings_flux2_klein_q6p

uv run python -m experiments.image_benchmark.benchmark_image_models resume --stage finalist_efficient --models cloudflare_flux2_klein --execute-remote --max-cost-usd 0.01
uv run python -m experiments.image_benchmark.benchmark_image_models resume --stage finalist_efficient --models gemini_flash_lite_image --execute-remote --max-cost-usd 0.41
uv run python -m experiments.image_benchmark.benchmark_image_models resume --stage finalist_efficient --models gemini_flash_image --execute-remote --max-cost-usd 0.81
uv run python -m experiments.image_benchmark.benchmark_image_models resume --stage finalist_efficient --models gemini_pro_image --execute-remote --max-cost-usd 1.61
```

These ceilings cover the configuration's twelve-image projections. They remain
authorization ceilings rather than billing budgets.

Use `resume` to skip jobs whose manifest and native/normalized output are
complete:

```bash
uv run python -m experiments.image_benchmark.benchmark_image_models resume \
  --stage finalist \
  --models icon_scene mflux_flux2_klein_q4
```

## Prepare local models

Preparation is explicit and downloads only named candidates:

```bash
uv run python -m experiments.image_benchmark.benchmark_image_models prepare \
  --models mflux_flux2_klein_q4 sdxl_turbo
```

The practical Z-Image profile for a 16 GB Apple Silicon machine uses the
pre-quantized 5.91 GB MFLUX checkpoint, not the roughly 33 GB reconstructed
Diffusers checkpoint:

```bash
uv run python -m experiments.image_benchmark.benchmark_image_models prepare \
  --models mflux_z_image_turbo_q4

uv run python -m experiments.image_benchmark.benchmark_image_models resume \
  --stage smoke \
  --models mflux_z_image_turbo_q4
```

It generates at 512×512 using nine steps, then follows the same 384px WebP
normalization path as every other candidate. It is a memory-tight comparison,
not the provisional default; avoid other memory-heavy applications while its
smoke run is active.

`uv` creates isolated environments and may install the requested Python on
first use. Weights remain in the normal Hugging Face cache. Individual models
can consume roughly 1–14 GB; preparing much of the catalog can exceed 30–50 GB.

Install Draw Things separately when testing it:

```bash
brew install drawthingsai/draw-things/draw-things-cli
draw-things-cli --help
```

Its model directory normally follows the Draw Things application. Override
`models_dir` in a local benchmark YAML when needed.

## Remote safety

Remote jobs require both `--execute-remote` and `--max-cost-usd`. The harness
checks the configured paid list-price projection before starting any runner:

Creating the token and finding the account id are in
[the providers guide](../providers.md#cloudflare-text-pictures-and-an-english-voice). Keep the token
out of shell history with `read -s "CLOUDFLARE_API_TOKEN?Cloudflare Workers AI token: "`.

```bash
export CLOUDFLARE_ACCOUNT_ID="..."
export CLOUDFLARE_API_TOKEN="..."
uv run python -m experiments.image_benchmark.benchmark_image_models run \
  --stage smoke \
  --models cloudflare_flux2_klein \
  --execute-remote \
  --max-cost-usd 0.01
```

For Vertex AI Gemini, reuse Application Default Credentials:

```bash
gcloud auth application-default login
gcloud config set project "your-project-id"
gcloud auth application-default set-quota-project "your-project-id"
gcloud services enable aiplatform.googleapis.com --project="your-project-id"
export GOOGLE_CLOUD_PROJECT="$(gcloud config get-value project)"
export GOOGLE_CLOUD_LOCATION="global"
```

Then select `gemini_flash_lite_image` or `gemini_flash_image`. The CLI ceiling
is not a provider billing budget; verify quotas and billing independently.
Vertex pay-as-you-go uses shared capacity, so a valid request can still receive
HTTP 429. The Gemini profiles make at most three attempts with bounded
exponential backoff. `resume` preserves completed images and retries only jobs
without a complete success manifest:

```bash
uv run python -m experiments.image_benchmark.benchmark_image_models resume \
  --stage smoke \
  --models gemini_flash_image \
  --execute-remote \
  --max-cost-usd 0.45
```

The printed `$0.402` is the conservative configured projection for all six
jobs, including successful jobs that `resume` will skip. It is not a statement
of actual billed cost.

The premium comparison uses Gemini 3 Pro Image, also called Nano Banana Pro.
Its configured six-image smoke projection is `$0.804` at 1K square output:

```bash
uv run python -m experiments.image_benchmark.benchmark_image_models resume \
  --stage smoke \
  --models gemini_pro_image \
  --execute-remote \
  --max-cost-usd 0.85
```

Gemini 3.1 Flash Image is already Nano Banana 2. Nano Banana Pro is the intended
next quality test; the older Gemini 2.5 Flash Image branding is not a quality
upgrade. Lite and Flash request 1K square PNG. Pro requests 2K square PNG to
mirror the successful Vim Mastery workflow; Google's current Pro pricing lists
the same image-output charge for 1K and 2K. Every result still follows the common
384px normalization path.

## Result contract

Each job directory contains:

- `request.json`: stable runner input.
- `runner-result.json`: backend result, versions, and provenance.
- `native.*`: untouched provider output.
- `native.sanitized.svg`: allowlisted SVG, where applicable.
- `normalized.webp`: 384×384 review/Anki-sized artifact.
- `resource-usage.txt`: macOS `/usr/bin/time -l` output when available.
- `manifest.json`: settings, timing, RSS, dimensions, sizes, cost, logs, and
  status.

Job IDs hash prompt, style, seed, candidate model/settings, and stage. A config
change therefore creates a distinct result instead of silently reusing media.

## macOS signal probe

Compile and run the diagnostic without installing a LaunchAgent:

```bash
swiftc tools/macos_idle_probe.swift -o /tmp/acervo-macos-idle-probe
/tmp/acervo-macos-idle-probe
/tmp/acervo-macos-idle-probe --watch --interval 1
```

If a restricted environment prevents Swift from writing its module cache, set
`CLANG_MODULE_CACHE_PATH` and `SWIFT_MODULECACHE_PATH` to temporary directories.
Validate while typing, using dictation, in Zoom/Meet, with camera on/off, and
while changing AC power. The probe never starts image generation.

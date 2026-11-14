"""Draw the full run in Vertex batch jobs: half the price, and no one-picture-a-minute limit.

One command does everything, and the same command carries on after any stop:

    caffeinate -i .venv/bin/python experiments/character-pictures/run.py batch --set common

1. Collect: every job submitted earlier and not yet collected is asked for its state; a finished
   one, including one that failed or was cancelled midway, is read, and each picture it drew is
   written to `out/full/pictures/` at once.
2. Submit: every picture still wanted — scripted, not on disk, not in a job in flight — goes into
   jobs of at most `--job-size` requests, most popular group first, up to `--budget` dollars.
3. Wait: every `--poll` seconds, collect what has finished, until nothing is left in flight.

The state of every job is in `out/full/batches.json`, written before a job is created and again as
soon as it is, so a stop at any moment never submits the same pictures twice. A job remembers which
provider (Google Cloud project) it ran in, so after switching with `--provider` the earlier jobs are
still collected from where they ran.

This is the experiment's apparatus, not the service's: the request is the one `acervo.models.call`
sends for a picture with a reference (the reference, then the prompt; the family's `imageConfig`
with a square aspect ratio; no seed), written out by hand because LiteLLM has no batch route for it.
The sign-in is the provider's own, through `acervo.models.google_auth`.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import sys
import time
import urllib.parse
from collections import defaultdict
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

import httpx

import run

STATE = run.OUT / "batches.json"
RUNNING = {"JOB_STATE_QUEUED", "JOB_STATE_PENDING", "JOB_STATE_RUNNING", "JOB_STATE_CANCELLING",
           "JOB_STATE_UPDATING", "JOB_STATE_PAUSED", "JOB_STATE_UNSPECIFIED"}
# Vertex list prices for Gemini 3.1 Flash Image, per million tokens: $0.50 in, $3 text out, $60
# picture out (a 1K picture is 1,120 tokens, $0.067). A batch job is billed at half.
PRICE_IN, PRICE_TEXT, PRICE_IMAGE, BATCH = 0.50, 3.0, 60.0, 0.5
STORAGE = "https://storage.googleapis.com"
TIMEOUT = 120.0


class Stop(Exception):
    """A reason the whole run must stop: a login, a setting, an account that cannot pay."""


# ── signed-in requests ──────────────────────────────────────────────────────


def _headers(row: Any) -> dict[str, str]:
    from acervo.models import google_auth
    from acervo.models.errors import ProviderRefused

    try:
        return google_auth.headers(row, run.MODEL.model)
    except ProviderRefused as refused:
        if refused.reason == "authentication":
            raise Stop(run.LOGIN_HINT) from None
        raise Stop(f"{row.id}: {refused}") from None


def _request(row: Any, method: str, url: str, **kwargs: Any) -> httpx.Response:
    """One call to a Google API, with the reasons to stop told apart from the reasons to wait."""
    headers = {**_headers(row), **kwargs.pop("headers", {})}
    try:
        response = httpx.request(method, url, headers=headers, timeout=TIMEOUT, **kwargs)
    except httpx.HTTPError as error:
        raise ConnectionError(f"{method} {url.split('?')[0]}: {error}") from None
    if response.is_success or response.status_code == 404:
        return response
    message = _message(response)
    lowered = message.lower()
    if "billing" in lowered or "credit" in lowered or "payment" in lowered:
        raise Stop(f"the account behind provider {row.id} cannot pay: {run._scrubbed(message)}. "
                   "Switch to another Google Cloud project with `--provider <id>` and rerun; "
                   "jobs already submitted are still collected from where they ran.")
    if response.status_code in (401, 403):
        if "reauth" in lowered or "invalid_grant" in lowered or "expired" in lowered:
            raise Stop(run.LOGIN_HINT)
        raise Stop(f"{row.id} was refused ({response.status_code}): {run._scrubbed(message)}")
    if response.status_code == 400:
        raise Stop(f"{row.id} refused the request as malformed: {run._scrubbed(message)}")
    raise ConnectionError(f"{response.status_code}: {run._scrubbed(message)}")


def _message(response: httpx.Response) -> str:
    try:
        payload = response.json()
        return str((payload.get("error") or {}).get("message") or payload)[:600]
    except ValueError:
        return response.text[:600]


# ── Cloud Storage ───────────────────────────────────────────────────────────


def _project(row: Any) -> str:
    project = row.setting("project")
    if not project:
        raise Stop(f"provider {row.id} names no Google Cloud project")
    return project


def bucket_for(row: Any) -> str:
    """Acervo's own bucket in the provider's project, created on first use. Nothing else is touched."""
    name = f"{_project(row)}-character-pictures"
    if _request(row, "GET", f"{STORAGE}/storage/v1/b/{name}").status_code == 404:
        run.say(f"creating the bucket gs://{name} (location US) for the batch jobs' files")
        response = _request(row, "POST", f"{STORAGE}/storage/v1/b",
                            params={"project": _project(row)},
                            json={"name": name, "location": "US",
                                  "iamConfiguration": {"uniformBucketLevelAccess": {"enabled": True}}})
        if response.status_code == 404:
            raise Stop(f"could not create gs://{name}: the project was not found")
    return name


def _upload(row: Any, bucket: str, name: str, data: bytes, kind: str) -> None:
    _request(row, "POST", f"{STORAGE}/upload/storage/v1/b/{bucket}/o",
             params={"uploadType": "media", "name": name}, content=data, headers={"Content-Type": kind})


def _list(row: Any, bucket: str, prefix: str) -> list[str]:
    names, token = [], None
    while True:
        params = {"prefix": prefix, "fields": "items(name),nextPageToken"}
        if token:
            params["pageToken"] = token
        payload = _request(row, "GET", f"{STORAGE}/storage/v1/b/{bucket}/o", params=params).json()
        names += [item["name"] for item in payload.get("items") or []]
        token = payload.get("nextPageToken")
        if not token:
            return names


def _lines(row: Any, bucket: str, name: str):
    """A JSONL object's lines, streamed: a job's output holds every picture, base64."""
    url = f"{STORAGE}/storage/v1/b/{bucket}/o/{urllib.parse.quote(name, safe='')}"
    with httpx.stream("GET", url, params={"alt": "media"}, headers=_headers(row), timeout=600.0) as response:
        if not response.is_success:
            raise ConnectionError(f"reading {name}: {response.status_code}")
        for line in response.iter_lines():
            if line.strip():
                yield line


def _delete(row: Any, bucket: str, names: list[str]) -> None:
    for name in names:
        _request(row, "DELETE", f"{STORAGE}/storage/v1/b/{bucket}/o/{urllib.parse.quote(name, safe='')}")


def reference_name(character: str) -> str:
    data = run.reference(character).read_bytes()
    return f"refs/{ord(character):x}-{hashlib.sha256(data).hexdigest()[:12]}.png"


def character_of(uri: str) -> str | None:
    """The character a request was for, from its reference's name (`refs/<codepoint>-<digest>.png`)."""
    try:
        return chr(int(uri.rsplit("/", 1)[-1].split("-", 1)[0], 16))
    except ValueError:
        return None


# ── Vertex batch jobs ───────────────────────────────────────────────────────


def _endpoint(row: Any) -> tuple[str, str]:
    location = row.setting("location") or "global"
    host = "aiplatform.googleapis.com" if location == "global" else f"{location}-aiplatform.googleapis.com"
    return f"https://{host}/v1/projects/{_project(row)}/locations/{location}", location


def _request_line(row: Any, bucket: str, character: str, text: str) -> dict[str, Any]:
    """The request `call.image` sends with a reference, in the batch file's shape."""
    params = row.params_for("image")
    config = {"responseModalities": ["IMAGE", "TEXT"],
              "imageConfig": {**(params.get("imageConfig") or {}), "aspectRatio": "1:1"}}
    return {"request": {
        "contents": [{"role": "user", "parts": [
            {"fileData": {"fileUri": f"gs://{bucket}/{reference_name(character)}", "mimeType": "image/png"}},
            {"text": text},
        ]}],
        "generationConfig": config,
    }}


def _find_job(row: Any, display: str) -> dict[str, Any] | None:
    base, _ = _endpoint(row)
    payload = _request(row, "GET", f"{base}/batchPredictionJobs",
                       params={"filter": f'display_name="{display}"'}).json()
    jobs = payload.get("batchPredictionJobs") or []
    return jobs[0] if jobs else None


def submit(row: Any, job: dict[str, Any], prompts: dict[str, str], known_refs: set[str]) -> None:
    """Upload a job's references and requests, then create it. The state is saved by the caller."""
    bucket = job["bucket"]
    characters = sorted({key.split("/")[0] for key in job["requests"]})
    for character in characters:
        name = reference_name(character)
        if name not in known_refs:
            _upload(row, bucket, name, run.reference(character).read_bytes(), "image/png")
            known_refs.add(name)
    body = "\n".join(json.dumps(_request_line(row, bucket, key.split("/")[0], prompts[key.split("/")[0]]),
                                ensure_ascii=False) for key in job["requests"]) + "\n"
    _upload(row, bucket, f"{job['prefix']}/input.jsonl", body.encode("utf-8"), "application/jsonl")
    base, _ = _endpoint(row)
    created = _request(row, "POST", f"{base}/batchPredictionJobs", json={
        "displayName": job["display"],
        "model": f"publishers/google/models/{run.MODEL.model}",
        "inputConfig": {"instancesFormat": "jsonl",
                        "gcsSource": {"uris": [f"gs://{bucket}/{job['prefix']}/input.jsonl"]}},
        "outputConfig": {"predictionsFormat": "jsonl",
                         "gcsDestination": {"outputUriPrefix": f"gs://{bucket}/{job['prefix']}/output"}},
    }).json()
    job["name"] = created["name"]
    job["state"] = created.get("state", "JOB_STATE_PENDING")


def refresh(row: Any, job: dict[str, Any]) -> None:
    base, _ = _endpoint(row)
    host = base.split("/v1/")[0]
    response = _request(row, "GET", f"{host}/v1/{job['name']}")
    if response.status_code == 404:
        job["state"] = "JOB_STATE_FAILED"
        job["error"] = "the job no longer exists"
        return
    payload = response.json()
    job["state"] = payload.get("state", job.get("state"))
    stats = payload.get("completionStats") or {}
    job["done"] = int(stats.get("successfulCount") or 0)
    job["failed"] = int(stats.get("failedCount") or 0)
    if payload.get("error"):
        job["error"] = run._scrubbed(str(payload["error"].get("message") or payload["error"]))


def _cost(usage: dict[str, Any]) -> float:
    if not usage:
        return run.MODEL.batch_usd
    image = sum(int(d.get("tokenCount") or 0) for d in usage.get("candidatesTokensDetails") or []
                if d.get("modality") == "IMAGE")
    text = int(usage.get("candidatesTokenCount") or 0) - image + int(usage.get("thoughtsTokenCount") or 0)
    spent = (int(usage.get("promptTokenCount") or 0) * PRICE_IN + max(text, 0) * PRICE_TEXT
             + image * PRICE_IMAGE) / 1e6
    return round(spent * BATCH, 5)


def harvest(row: Any, job: dict[str, Any]) -> tuple[int, int]:
    """Write every picture a finished job drew; a refusal or failure is logged and left missing.

    The k-th answer for a character fills that character's k-th take in the job, in the output's own
    order, and a take already on disk is skipped, so reading a job twice writes nothing twice.
    """
    from acervo.images.render import encode_master

    wanted: dict[str, list[int]] = defaultdict(list)
    for key in job["requests"]:
        character, take = key.split("/")
        wanted[character].append(int(take))
    seen: dict[str, int] = defaultdict(int)
    drawn = refused = 0
    names = _list(row, job["bucket"], f"{job['prefix']}/output")
    for name in sorted(n for n in names if n.endswith(".jsonl")):
        for raw in _lines(row, job["bucket"], name):
            line = json.loads(raw)
            parts = (((line.get("request") or {}).get("contents") or [{}])[0].get("parts")) or []
            uri = next((p["fileData"]["fileUri"] for p in parts if "fileData" in p), "")
            character = character_of(uri)
            if character not in wanted:
                continue
            index = seen[character]
            seen[character] += 1
            if index >= len(wanted[character]):
                continue
            take = wanted[character][index]
            target = run.picture_path(character, run.MODEL.id, "edit", take)
            if target.exists():
                continue
            entry = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "model": run.MODEL.id,
                     "wire": run.MODEL.model, "route": "batch", "provider": row.id, "job": job["display"],
                     "character": character, "way": "edit", "take": take}
            response = line.get("response") or {}
            candidate = (response.get("candidates") or [{}])[0]
            image = next((p["inlineData"] for p in (candidate.get("content") or {}).get("parts") or []
                          if "inlineData" in p and str(p["inlineData"].get("mimeType", "")).startswith("image/")), None)
            if not image:
                said = " ".join(p.get("text", "") for p in (candidate.get("content") or {}).get("parts") or [])
                reason = line.get("status") or candidate.get("finishReason") or "no image"
                run.log({**entry, "error": "refused", "message": f"{reason}: {said}".strip()})
                refused += 1
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(encode_master(base64.b64decode(image["data"])))
            run.log({**entry, "costUsd": _cost(response.get("usageMetadata") or {}),
                     "tokens": response.get("usageMetadata") or {}})
            drawn += 1
    job["harvested"] = True
    job["drawn"], job["refused"] = drawn, refused
    _delete(row, job["bucket"], names + [f"{job['prefix']}/input.jsonl"])
    return drawn, refused


# ── the state ───────────────────────────────────────────────────────────────


def load() -> dict[str, Any]:
    return json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"jobs": []}


def save(state: dict[str, Any]) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    temporary.replace(STATE)


def _refusals() -> dict[str, int]:
    """How often each character came back without a picture. One refused twice is skipped."""
    path = run.OUT / "draws.jsonl"
    counts: dict[str, int] = defaultdict(int)
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            entry = json.loads(line)
            if entry.get("error") == "refused":
                counts[entry["character"]] += 1
    return counts


# ── the command ─────────────────────────────────────────────────────────────


def _plan(args: argparse.Namespace, chosen: list[dict[str, Any]], state: dict[str, Any],
          allowance: float | None = None) -> list[tuple[str, str]]:
    """(group, 'character/take') for every picture to submit now, most popular first."""
    in_flight = {key for job in state["jobs"] if not job.get("harvested") for key in job["requests"]}
    refused = _refusals()
    plan = []
    for character, _way, take in run._wanted(run.MODEL, chosen, redraw=args.redraw, takes=args.takes):
        key = f"{character}/{take}"
        if key in in_flight or run.picture_path(character, run.MODEL.id, "edit", take).exists():
            continue
        if refused.get(character, 0) >= 2 and not args.characters:
            continue
        plan.append((next(e["group"] for e in chosen if e["character"] == character), key))
    if args.budget is not None:
        plan = plan[: max(0, math.floor(args.budget / run.MODEL.batch_usd))]
    if allowance is not None:
        plan = plan[: max(0, math.floor(allowance / run.MODEL.batch_usd))]
    return plan


def _new_jobs(row: Any, bucket: str, plan: list[tuple[str, str]], size: int,
              state: dict[str, Any], remembered: dict[str, str] | None = None) -> list[dict[str, Any]]:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dt%H%M%S")
    by_group: dict[str, list[str]] = defaultdict(list)
    for group, key in plan:
        by_group[group].append(key)
    jobs = []
    number = len(state["jobs"])
    for group, keys in by_group.items():
        for start in range(0, len(keys), size):
            number += 1
            display = f"character-pictures-{group}-{number:03d}-{stamp}"
            jobs.append({"display": display, "group": group, "provider": row.id, "bucket": bucket,
                         "prefix": f"jobs/{display}", "requests": keys[start:start + size],
                         "name": None, "state": "SUBMITTING", "harvested": False, "account": remembered,
                         "submitted": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    return jobs


def _rows() -> dict[str, Any]:
    from acervo.models.local import load_local

    return {row.id: row for row in load_local().rows}


ADC = Path.home() / ".config" / "gcloud" / "application_default_credentials.json"
# The one Google Cloud project this experiment may bill, in an ignored file: a project id is private.
BILLING = run.HERE / "billing.local.json"


def guard(row: Any) -> None:
    """Refuse to bill any project but the one `billing.local.json` names."""
    if not BILLING.exists():
        raise Stop(f"no {BILLING.name} beside run.py: write {{\"project\": \"<id>\"}} naming the one Google "
                   "Cloud project this experiment may bill")
    allowed = json.loads(BILLING.read_text(encoding="utf-8")).get("project")
    project = row.setting("project")
    if not allowed or project != allowed:
        raise Stop(f"this would bill project {project}, but {BILLING.name} allows only {allowed}. Switch the "
                   f"shell's account (`gcp-<profile>`) or pass the right `--provider`/`--project`.")


def account(project: str | None, credentials: str | None) -> tuple[Any, dict[str, str]]:
    """A Google Cloud account not in providers.local.json: the shell's current sign-in, or a project
    named on the command line, as a provider row. Also what a job keeps to find it again.

    The credentials file is `--credentials`, else `GOOGLE_APPLICATION_CREDENTIALS` (what `gcp-<profile>`
    sets), else gcloud's application-default file. The project is `--project`, else
    `GOOGLE_CLOUD_PROJECT`, else gcloud's active configuration, else the file's quota project.
    """
    import os
    import subprocess

    from acervo.models.providers import build

    path = Path(credentials or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or ADC).expanduser()
    if not path.exists():
        raise Stop(f"no Google credentials file at {path}: run `gcloud auth application-default login`, "
                   "or switch with `gcp-<profile>`, or pass `--credentials`")
    info = json.loads(path.read_text(encoding="utf-8"))
    if not project:
        project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project:
        try:
            project = subprocess.run(["gcloud", "config", "get-value", "project"], capture_output=True,
                                     text=True, timeout=30).stdout.strip() or None
        except (OSError, subprocess.TimeoutExpired):
            project = None
    project = project or info.get("quota_project_id")
    if not project:
        raise Stop("no Google Cloud project: pass `--project <id>`")
    # The id goes into the call log, which is committed; a project id is not, so it is hashed.
    identifier = f"gcloud-{hashlib.sha256(project.encode()).hexdigest()[:8]}"
    document = {"id": identifier, "family": "google-cloud", "settings": {"project": project},
                "models": {"image": [run.MODEL.model]}, "position": 0}
    providers, refused = build([document], {identifier: {"credentials": info}})
    if refused:
        raise Stop(f"the credentials in {path} were refused: {refused[0][1]}")
    return providers.rows[0], {"project": project, "credentials": str(path)}


def _row_for(job: dict[str, Any], rows: dict[str, Any]) -> Any:
    """The provider a job ran in: a providers.local.json row, or the account it remembers."""
    if job["provider"] in rows:
        return rows[job["provider"]]
    if job.get("account"):
        row, _ = account(job["account"]["project"], job["account"]["credentials"])
        rows[row.id] = row
        return row
    return None


def _collect(state: dict[str, Any], rows: dict[str, Any]) -> list[dict[str, Any]]:
    """Ask every job in flight for its state; collect the finished ones. The ones still running."""
    running = []
    for job in state["jobs"]:
        if job.get("harvested"):
            continue
        row = _row_for(job, rows)
        if row is None:
            run.say(f"{job['display']}: its provider {job['provider']!r} is no longer in providers.local.json; skipped")
            continue
        if not job.get("name"):
            found = _find_job(row, job["display"])
            if not found:
                # Saved before creation and never created: nothing to collect, nothing spent.
                job["harvested"], job["state"] = True, "NEVER_CREATED"
                save(state)
                continue
            job["name"] = found["name"]
        try:
            refresh(row, job)
        except ConnectionError as error:
            run.say(f"{job['display']}: could not ask for its state ({error}); trying again later")
            running.append(job)
            continue
        if job["state"] in RUNNING:
            running.append(job)
            continue
        drawn, refused = harvest(row, job)
        save(state)
        note = f"; {job['error']}" if job.get("error") else ""
        run.say(f"{job['display']}: {job['state'].removeprefix('JOB_STATE_').lower()}, "
                f"{drawn} pictures written, {refused} refused{note}")
        if job.get("error") and any(word in job["error"].lower() for word in ("billing", "credit", "payment")):
            raise Stop(f"job {job['display']} stopped because the account behind {row.id} cannot pay: "
                       f"{job['error']}. Its finished pictures are written. Switch with `--provider <id>`.")
    return running


def resolve(args: argparse.Namespace, rows: dict[str, Any]) -> tuple[Any, dict[str, str] | None]:
    """The account to submit to: `--provider current`, `--project`, or a providers.local.json id."""
    if args.provider == "current" or args.project or args.credentials:
        row, remembered = account(args.project, args.credentials)
        rows[row.id] = row
        run.say(f"account: Google Cloud project {remembered['project']}, credentials {Path(remembered['credentials']).name}")
        return row, remembered
    provider = args.provider or run.MODEL.provider
    if provider not in rows:
        sys.exit(f"No provider {provider!r} in providers.local.json; its ids are: {', '.join(rows)}, "
                 "or `--provider current` for the shell's current Google Cloud account")
    row = rows[provider]
    if row.reason():
        sys.exit(f"{provider} cannot be called from this machine: {row.reason()}.")
    return row, None


def spent_through(provider: str, state: dict[str, Any]) -> tuple[float, float]:
    """Dollars already spent through a provider (the call log), and still in flight there."""
    spent = 0.0
    path = run.OUT / "draws.jsonl"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            entry = json.loads(line)
            if entry.get("provider") == provider and entry.get("costUsd"):
                spent += entry["costUsd"]
    flying = sum(len(job["requests"]) for job in state["jobs"]
                 if job["provider"] == provider and not job.get("harvested")) * run.MODEL.batch_usd
    return spent, flying


def run_batch(args: argparse.Namespace) -> None:
    chosen = run.prepare(args)
    rows = _rows()
    row, remembered = resolve(args, rows)
    guard(row)
    state = load()
    prompts = run.prompts_for(chosen)

    running = _collect(state, rows)
    allowance = None
    if args.cap is not None:
        spent, flying = spent_through(row.id, state)
        allowance = max(0.0, args.cap - spent - flying)
        run.say(f"cap ${args.cap:.2f} on this account: ${spent:.2f} spent, ${flying:.2f} in flight, "
                f"${allowance:.2f} left to submit")
    plan = _plan(args, chosen, state, allowance)
    usd = len(plan) * run.MODEL.batch_usd
    groups = defaultdict(int)
    for group, _key in plan:
        groups[group] += 1
    run.say(f"to submit: {len(plan)} pictures, about ${usd:.2f} in batch, "
            + (", ".join(f"{g} {n}" for g, n in groups.items()) or "nothing")
            + f"; {sum(len(j['requests']) for j in running)} pictures in {len(running)} jobs already in flight")
    if args.dry_run:
        return
    if plan:
        bucket = bucket_for(row)
        known = set(_list(row, bucket, "refs/"))
        pending = _new_jobs(row, bucket, plan, args.job_size, state, remembered)
        for job in pending:
            state["jobs"].append(job)
            save(state)  # before creating it: a stop in between is found again by its name
            try:
                submit(row, job, prompts, known)
            except ConnectionError as error:
                # Most likely the limit on jobs at once: leave it for the next round of collecting.
                state["jobs"].remove(job)
                save(state)
                run.say(f"could not submit {job['display']} now ({error}); a rerun submits it")
                break
            save(state)
            running.append(job)
            run.say(f"submitted {job['display']}: {len(job['requests'])} pictures")
    if args.no_wait:
        run.say("not waiting; rerun the same command to collect the jobs when they are done")
        return
    while running:
        summary = ", ".join(f"{j['display'].split('-')[2]}-{j['display'].split('-')[3]} "
                            f"{j.get('state', '?').removeprefix('JOB_STATE_').lower()} "
                            f"{j.get('done', 0)}/{len(j['requests'])}" for j in running)
        run.say(f"waiting {args.poll:.0f} s: {summary}")
        time.sleep(args.poll)
        running = _collect(state, rows)
    missing = sum(not run.picture_path(c, run.MODEL.id, "edit", t).exists()
                  for c, _w, t in run._wanted(run.MODEL, chosen, redraw=args.redraw, takes=args.takes))
    run.say(f"done; {missing} pictures of this set still missing"
            + (" — run the same command again to submit them" if missing else ""))


def main(args: argparse.Namespace) -> None:
    try:
        run_batch(args)
    except Stop as stop:
        print(f"STOPPED: {stop}", flush=True)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nStopped here. Jobs already submitted keep running at Google; run the same command "
              "again to collect them.", flush=True)

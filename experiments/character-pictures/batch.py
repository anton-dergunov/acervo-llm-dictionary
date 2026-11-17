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
import threading
import time
import urllib.parse
from collections import Counter, defaultdict
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

import httpx

import run

STATE = run.OUT / "batches.json"
RUNNING = {"JOB_STATE_QUEUED", "JOB_STATE_PENDING", "JOB_STATE_RUNNING", "JOB_STATE_CANCELLING",
           "JOB_STATE_UPDATING", "JOB_STATE_PAUSED", "JOB_STATE_UNSPECIFIED"}
# A batch job or a Flex call is billed at half each model's list price (`run.Model`; a 1K picture is
# 1,120 tokens, $0.067 from Nano Banana 2 at the standard tier).
BATCH = 0.5
# What a picture in flight holds back from the cap until its real cost is logged: above the $0.0336
# measured, so the cap is never crossed by an estimate.
PICTURE_RESERVE = 0.04
STORAGE = "https://storage.googleapis.com"
TIMEOUT = 120.0
HISTORY = 50            # how many changes of a job's picture count are kept, for its progress line
STALL_MINUTES = 90      # a running job with no new picture for this long is called stalled


class Stop(Exception):
    """A reason the whole run must stop: a login, a setting, an account that cannot pay."""


# ── signed-in requests ──────────────────────────────────────────────────────


def _headers(row: Any) -> dict[str, str]:
    from acervo.models import google_auth
    from acervo.models.errors import ProviderRefused

    try:
        found = google_auth.headers(row, run.MODEL.model)
    except ProviderRefused as refused:
        if refused.reason == "authentication":
            raise Stop(run.LOGIN_HINT) from None
        raise Stop(f"{row.id}: {refused}") from None
    guard(row, found)
    return found


def _request(row: Any, method: str, url: str, timeout: float = TIMEOUT, **kwargs: Any) -> httpx.Response:
    """One call to a Google API, with the reasons to stop told apart from the reasons to wait."""
    headers = {**_headers(row), **kwargs.pop("headers", {})}
    try:
        response = httpx.request(method, url, headers=headers, timeout=timeout, **kwargs)
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
    response = _request(row, "GET", f"{STORAGE}/storage/v1/b/{name}")
    if response.status_code == 404:
        run.say(f"creating the bucket gs://{name} (location US) for the batch jobs' files")
        response = _request(row, "POST", f"{STORAGE}/storage/v1/b",
                            params={"project": _project(row)},
                            json={"name": name, "location": "US",
                                  "iamConfiguration": {"uniformBucketLevelAccess": {"enabled": True}}})
        if response.status_code == 404:
            raise Stop(f"could not create gs://{name}: the project was not found")
    number = str(response.json().get("projectNumber") or "")
    if not number:
        raise Stop(f"gs://{name} does not say which project it belongs to")
    _numbers[row.id] = number
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
    create_job(row, job, body, job_model(job).model)


def job_model(job: dict[str, Any]) -> run.Model:
    """The model a picture job draws with, which every job names."""
    return run.model_by_id(job["model"])


def create_job(row: Any, job: dict[str, Any], body: str, model: str) -> None:
    """Upload a job's requests and create it; the state is saved by the caller.

    A job created under any project number but the bucket's (the allowed project's) is cancelled
    at once and the run stops.
    """
    bucket = job["bucket"]
    _upload(row, bucket, f"{job['prefix']}/input.jsonl", body.encode("utf-8"), "application/jsonl")
    base, _ = _endpoint(row)
    created = _request(row, "POST", f"{base}/batchPredictionJobs", json={
        "displayName": job["display"],
        "model": f"publishers/google/models/{model}",
        "inputConfig": {"instancesFormat": "jsonl",
                        "gcsSource": {"uris": [f"gs://{bucket}/{job['prefix']}/input.jsonl"]}},
        "outputConfig": {"predictionsFormat": "jsonl",
                         "gcsDestination": {"outputUriPrefix": f"gs://{bucket}/{job['prefix']}/output"}},
    }).json()
    job["name"] = created["name"]
    job["state"] = created.get("state", "JOB_STATE_PENDING")
    number = _numbers.get(row.id)
    if not number or not job["name"].startswith(f"projects/{number}/"):
        host = base.split("/v1/")[0]
        _request(row, "POST", f"{host}/v1/{job['name']}:cancel")
        raise Stop(f"job {job['display']} was created outside the allowed project (its bucket's project "
                   "number differs); it was cancelled at once")


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
    history = job.setdefault("progress", [])
    if not history or history[-1][1] != job["done"]:
        history.append([_now().isoformat(timespec="seconds"), job["done"]])
        del history[:-HISTORY]
    if payload.get("error"):
        job["error"] = run._scrubbed(str(payload["error"].get("message") or payload["error"]))


def _cost(usage: dict[str, Any], model: run.Model | None = None) -> float:
    """What one answer cost in a batch job or through Flex (both half the list price)."""
    model = model or run.MODEL
    if not usage:
        return model.batch_usd
    image = sum(int(d.get("tokenCount") or 0) for d in usage.get("candidatesTokensDetails") or []
                if d.get("modality") == "IMAGE")
    text = int(usage.get("candidatesTokenCount") or 0) - image + int(usage.get("thoughtsTokenCount") or 0)
    spent = (int(usage.get("promptTokenCount") or 0) * model.price_in + max(text, 0) * model.price_text
             + image * model.price_image) / 1e6
    return round(spent * BATCH, 5)


def _picture_of(line: dict[str, Any], job_error: str | None = None) -> tuple[str, Any]:
    """What one answer holds: ("image", bytes), ("refused", why) or ("unfinished", why).

    A row the model never answered (no candidate and no prompt feedback) is unfinished, not refused.
    `line` is a batch output line, or `{"response": ...}` for a single call.
    """
    response = line.get("response") or {}
    candidate = (response.get("candidates") or [{}])[0]
    image = next((p["inlineData"] for p in (candidate.get("content") or {}).get("parts") or []
                  if "inlineData" in p and str(p["inlineData"].get("mimeType", "")).startswith("image/")), None)
    if not image and not candidate and not response.get("promptFeedback"):
        return "unfinished", line.get("status") or job_error or "the job ended before this row ran"
    if not image:
        said = " ".join(p.get("text", "") for p in (candidate.get("content") or {}).get("parts") or [])
        reason = line.get("status") or candidate.get("finishReason") or (response.get("promptFeedback") or {}).get("blockReason") or "no image"
        return "refused", f"{reason}: {said}".strip()
    return "image", base64.b64decode(image["data"])


def harvest(row: Any, job: dict[str, Any]) -> tuple[int, int, int]:
    """Write every picture a finished job drew; a refusal or failure is logged and left missing.
    (drawn, refused, unfinished).

    A row the model never answered (no candidate and no prompt feedback) is `unfinished`, not
    refused: Vertex ends a job 24 hours after it starts and returns its unprocessed rows empty. Only
    a refusal counts toward skipping a character (`_refusals`); an unfinished take is simply asked
    for again.

    The k-th answer for a character fills that character's k-th take in the job, in the output's own
    order, and a take already on disk is skipped, so reading a job twice writes nothing twice.
    """
    from acervo.images.render import encode_master

    model = job_model(job)
    wanted: dict[str, list[int]] = defaultdict(list)
    for key in job["requests"]:
        character, take = key.split("/")
        wanted[character].append(int(take))
    seen: dict[str, int] = defaultdict(int)
    drawn = refused = unfinished = 0
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
            target = run.picture_path(character, model.id, "edit", take)
            if target.exists():
                continue
            entry = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "model": model.id,
                     "wire": model.model, "route": "batch", "provider": row.id, "job": job["display"],
                     "character": character, "way": "edit", "take": take}
            kind, found = _picture_of(line, job.get("error"))
            if kind == "unfinished":
                run.log({**entry, "error": "unfinished", "message": found})
                unfinished += 1
                continue
            if kind == "refused":
                run.log({**entry, "error": "refused", "message": found})
                refused += 1
                continue
            usage = (line.get("response") or {}).get("usageMetadata") or {}
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(encode_master(found))
            run.log({**entry, "costUsd": _cost(usage, model), "tokens": usage})
            drawn += 1
    job["harvested"] = True
    job["drawn"], job["refused"], job["unfinished"] = drawn, refused, unfinished
    _delete(row, job["bucket"], names + [f"{job['prefix']}/input.jsonl"])
    return drawn, refused, unfinished


# ── Flex PayGo: single calls at the batch price ─────────────────────────────

# Flex only, never the standard tier: without `shared`, a project with Provisioned Throughput would
# spend that first. The server waits up to 30 minutes for capacity (its maximum).
FLEX_HEADERS = {"X-Vertex-AI-LLM-Request-Type": "shared",
                "X-Vertex-AI-LLM-Shared-Request-Type": "flex",
                "X-Server-Timeout": "1800"}
FLEX_TIMEOUT = 1860.0


def _traffic(payload: dict[str, Any]) -> str:
    return str(payload.get("trafficType") or (payload.get("usageMetadata") or {}).get("trafficType") or "")


def flex_one(row: Any, model: run.Model, bucket: str, character: str, take: int, text: str,
             stop: Any, deadline: float) -> str:
    """Draw one picture through Flex PayGo: "drawn", "refused" or "gave up". Raises Stop when the
    answer was not billed as Flex (it would be at twice the price) or the account cannot go on.

    A busy answer (429, 5xx, a dropped connection) costs nothing, so it is asked again until the
    deadline (`time.monotonic()`), resting 1 minute, then twice as long each time, at most 10."""
    from acervo.images.render import encode_master

    base, location = _endpoint(row)
    if location != "global":
        raise Stop(f"Flex PayGo is served on the global endpoint only, not {location}")
    url = f"{base}/publishers/google/models/{model.model}:generateContent"
    body = _request_line(row, bucket, character, text)["request"]
    entry = {"model": model.id, "wire": model.model, "route": "flex", "provider": row.id,
             "character": character, "way": "edit", "take": take}
    rest, began = run.FIRST_REST, time.monotonic()
    while time.monotonic() < deadline:
        if stop.is_set():
            return "gave up"
        started = time.monotonic()
        try:
            response = _request(row, "POST", url, timeout=FLEX_TIMEOUT, json=body, headers=FLEX_HEADERS)
        except ConnectionError as error:
            run.log({**entry, "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                     "error": "busy", "message": str(error),
                     "seconds": round(time.monotonic() - started, 1)})
            run.say(f"flex {character}-{take}: {run._scrubbed(str(error))[:120]}; resting {rest:.0f} s")
            stop.wait(rest)
            rest = min(rest * 2, run.LONGEST_REST)
            continue
        if response.status_code == 404:
            raise Stop(f"{model.model} is not served through Flex here: {run._scrubbed(_message(response))}")
        payload = response.json()
        traffic = _traffic(payload)
        if traffic != "ON_DEMAND_FLEX":
            raise Stop(f"a Flex call for {character} was served as {traffic or 'an unnamed tier'}, "
                       "not ON_DEMAND_FLEX, so it may be billed at full price; stopped")
        usage = payload.get("usageMetadata") or {}
        line = {**entry, "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "seconds": round(time.monotonic() - started, 1),
                "waited": round(time.monotonic() - began, 1), "trafficType": traffic,
                "costUsd": _cost(usage, model), "tokens": usage}
        kind, found = _picture_of({"response": payload})
        if kind != "image":
            run.log({**line, "error": "refused", "message": found})
            run.say(f"flex {character}-{take}: no picture ({run._scrubbed(str(found))[:120]})")
            return "refused"
        target = run.picture_path(character, model.id, "edit", take)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(encode_master(found))
        run.log(line)
        run.say(f"flex {character}-{take} in {line['seconds']:.0f} s (${line['costUsd']:.4f})")
        return "drawn"
    run.say(f"flex {character}-{take}: still busy at the deadline; a rerun tries it again")
    return "gave up"


def flex(row: Any, model: run.Model, work: list[tuple[str, int]], prompts: dict[str, str],
         workers: int = 4, hours: float = 1.0) -> Counter:
    """Draw (character, take) pairs through Flex, a few calls at once, asking again on a busy answer
    for at most `hours`. Counts of each outcome."""
    deadline = time.monotonic() + hours * 3600
    from concurrent.futures import ThreadPoolExecutor

    bucket = bucket_for(row)
    known = set(_list(row, bucket, "refs/"))
    for character in sorted({c for c, _t in work}):
        name = reference_name(character)
        if name not in known:
            _upload(row, bucket, name, run.reference(character).read_bytes(), "image/png")
            known.add(name)
    stop = threading.Event()
    stopped: list[Stop] = []

    def one(pair: tuple[str, int]) -> str:
        character, take = pair
        if run.picture_path(character, model.id, "edit", take).exists():
            return "on disk"
        try:
            return flex_one(row, model, bucket, character, take, prompts[character], stop, deadline)
        except Stop as reason:
            stopped.append(reason)
            stop.set()
            return "stopped"

    with ThreadPoolExecutor(max_workers=workers) as pool:
        outcomes = Counter(pool.map(one, work))
    if stopped:
        raise stopped[0]
    return outcomes


# ── the state ───────────────────────────────────────────────────────────────


def load(path: Path = STATE) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"jobs": []}


def save(state: dict[str, Any], path: Path = STATE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    temporary.replace(path)


def _refusals() -> dict[str, int]:
    """How often each character came back without a picture. One refused twice is skipped."""
    path = run.OUT / "draws.jsonl"
    counts: dict[str, int] = defaultdict(int)
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            entry = json.loads(line)
            if entry.get("error") == "refused" and entry.get("model", run.MODEL.id) == run.MODEL.id:
                counts[entry["character"]] += 1
    return counts


# ── the command ─────────────────────────────────────────────────────────────


def _plan(args: argparse.Namespace, chosen: list[dict[str, Any]], state: dict[str, Any],
          allowance: float | None = None) -> list[tuple[str, str]]:
    """(group, 'character/take') for every picture to submit now, most popular first."""
    in_flight = {key for job in state["jobs"] if not job.get("harvested") for key in job["requests"]}
    refused = _refusals()
    plan = []
    # A full-run script is drawn only once Argon has checked it against the scholarly origin.
    chosen = [entry for entry in chosen if entry.get("checked")]
    for character, _way, take in run._wanted(run.MODEL, chosen, redraw=args.redraw, takes=args.takes):
        key = f"{character}/{take}"
        if key in in_flight or run.picture_path(character, run.MODEL.id, "edit", take).exists():
            continue
        if refused.get(character, 0) >= 2 and not args.characters:
            continue
        plan.append((next(e["group"] for e in chosen if e["character"] == character), key))
    if getattr(args, "budget", None) is not None:
        plan = plan[: max(0, math.floor(args.budget / PICTURE_RESERVE))]
    if allowance is not None:
        plan = plan[: max(0, math.floor(allowance / PICTURE_RESERVE))]
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
                         "prefix": f"jobs/{display}", "requests": keys[start:start + size], "model": run.MODEL.id,
                         "name": None, "state": "SUBMITTING", "harvested": False, "account": remembered,
                         "submitted": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    return jobs


def _rows() -> dict[str, Any]:
    from acervo.models.local import load_local

    return {row.id: row for row in load_local().rows}


ADC = Path.home() / ".config" / "gcloud" / "application_default_credentials.json"
# The one Google Cloud project this experiment may bill, in an ignored file: a project id is private.
BILLING = run.HERE / "billing.local.json"


_numbers: dict[str, str] = {}   # provider id → the allowed project's number, read off its bucket
_verified: set[str] = set()     # digests of access tokens whose account was checked


def _tokeninfo(token: str) -> dict[str, Any]:
    try:
        answer = httpx.post("https://oauth2.googleapis.com/tokeninfo", data={"access_token": token}, timeout=60.0)
    except httpx.HTTPError as error:
        raise ConnectionError(f"asking Google whose sign-in this is: {error}") from None
    return answer.json() if answer.is_success else {}


_accounts: dict[str, str | None] = {}


def _account_of(info: dict[str, Any]) -> str | None:
    """The account a credentials file signs in as. A billing token is scoped to Cloud only and names
    no account, so a second token is asked for from the same file, scoped to the account's email."""
    if info.get("type") == "service_account":
        return info.get("client_email")
    key = hashlib.sha256(json.dumps(info, sort_keys=True).encode()).hexdigest()
    if key not in _accounts:
        import google.auth.exceptions
        import google.auth.transport.requests
        from google.oauth2 import credentials as user

        try:
            found = user.Credentials.from_authorized_user_info(
                info, scopes=["openid", "https://www.googleapis.com/auth/userinfo.email"])
            found.refresh(google.auth.transport.requests.Request())
        except google.auth.exceptions.RefreshError:
            raise Stop(run.LOGIN_HINT) from None
        except (ValueError, google.auth.exceptions.GoogleAuthError) as error:
            raise Stop(f"the credentials file could not be read: {error}") from None
        _accounts[key] = _tokeninfo(str(found.token)).get("email")
    return _accounts[key]


def billing() -> dict[str, Any]:
    """The one Google Cloud account this experiment may bill, and the most it may spend there.

    `{"project": "<id>", "account": "<email>", "profile": "<gcp profile>", "cap": <dollars>}`, in an
    ignored file: a project id and an email are private.
    """
    if not BILLING.exists():
        raise Stop(f"no {BILLING.name} beside run.py: write {{\"project\": \"<id>\", \"account\": \"<email>\", "
                   "\"cap\": <dollars>}} naming the one Google Cloud account this experiment may bill")
    settings = json.loads(BILLING.read_text(encoding="utf-8"))
    for field in ("project", "account", "cap"):
        if not settings.get(field):
            raise Stop(f"{BILLING.name} names no `{field}`")
    return settings


def guard(row: Any, headers: dict[str, str] | None = None) -> None:
    """Refuse to bill any project, or sign in as any account, but the ones `billing.local.json` names.

    Called before anything is planned and again by every signed-in request (`_headers`): the
    project the request bills, the shell's profile, and the account the token itself belongs to
    (asked of Google once per credentials file; each new token is checked to come from it).
    """
    import os

    settings = billing()
    project = row.setting("project")
    if project != settings["project"]:
        raise Stop(f"this would bill project {project}, but {BILLING.name} allows only {settings['project']}. "
                   "Switch the shell's account (`gcp use <profile>`) and use `--provider current`.")
    if settings.get("profile") and os.environ.get("GCP_PROFILE") != settings["profile"]:
        raise Stop(f"the shell's Google Cloud profile is {os.environ.get('GCP_PROFILE') or 'not set'}, but "
                   f"{BILLING.name} allows only {settings['profile']}: run `gcp use {settings['profile']}` first")
    if headers is None:
        headers = _headers(row)  # comes back here with the token
        return
    if "x-goog-api-key" in headers:
        raise Stop(f"provider {row.id} signs in with a key, which cannot be tied to an account; "
                   "use the account's own sign-in (`--provider current`)")
    if headers.get("x-goog-user-project") != settings["project"]:
        raise Stop(f"the request would charge quota project {headers.get('x-goog-user-project')}, "
                   f"not {settings['project']}")
    token = headers.get("Authorization", "").removeprefix("Bearer ")
    digest = hashlib.sha256(token.encode()).hexdigest()
    if digest in _verified:
        return
    info = dict(row.credential.file or {})
    email = _account_of(info)
    if email != settings["account"]:
        raise Stop(f"the credentials sign in as {email or 'an unknown account'}, but {BILLING.name} allows "
                   f"only {settings['account']}: run `gcp use {settings.get('profile') or '<profile>'}`")
    # The token that bills was minted from that same file: Google names the client it was issued to.
    issued = _tokeninfo(token)
    expected = info.get("client_id") if info.get("type") == "authorized_user" else info.get("client_id") or issued.get("azp")
    if not issued or issued.get("azp") != expected:
        raise Stop("Google could not confirm that the billing token comes from the checked credentials")
    _verified.add(digest)


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


def _collect(state: dict[str, Any], rows: dict[str, Any], path: Path = STATE) -> list[dict[str, Any]]:
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
                save(state, path)
                continue
            job["name"] = found["name"]
        try:
            refresh(row, job)
        except ConnectionError as error:
            run.say(f"{job['display']}: could not ask for its state ({error}); trying again later")
            running.append(job)
            continue
        if job["state"] in RUNNING:
            save(state, path)  # so batches.json and `run.py status` show the live count, not the state at submit
            running.append(job)
            continue
        drawn, refused, unfinished = harvest(row, job)
        save(state, path)
        note = f"; {job['error']}" if job.get("error") else ""
        run.say(f"{job['display']}: {job['state'].removeprefix('JOB_STATE_').lower()}, "
                f"{drawn} pictures written, {refused} refused, {unfinished} unfinished (asked for again){note}")
        if job.get("error") and any(word in job["error"].lower() for word in ("billing", "credit", "payment")):
            raise Stop(f"job {job['display']} stopped because the account behind {row.id} cannot pay: "
                       f"{job['error']}. Its finished pictures are written. Switch with `--provider <id>`.")
    return running


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _minutes(since: str, now: datetime) -> int:
    return max(0, int((now - datetime.fromisoformat(since)).total_seconds() // 60))


def _span(minutes: int) -> str:
    if minutes < 90:
        return f"{minutes} min"
    if minutes < 48 * 60:
        return f"{minutes / 60:.1f} h"
    return f"{minutes / 1440:.1f} d"


def running_jobs(path: Path = STATE) -> list[dict[str, Any]]:
    """The picture jobs not yet collected, as the run last saved them."""
    return [job for job in load(path)["jobs"] if not job.get("harvested")]


def job_progress(job: dict[str, Any], now: datetime | None = None) -> str:
    """One line on a running picture job: how far it is, the last hour, how long since a picture.

    Says STALLED? after `STALL_MINUTES` without a new picture (a job still at 0 counts from its
    submission). Only information: nothing is cancelled.
    """
    now = now or _now()
    done, total = int(job.get("done") or 0), len(job["requests"])
    history = job.get("progress") or []
    hour_ago = [count for when, count in history if _minutes(when, now) >= 60]
    gained = done - (hour_ago[-1] if hour_ago else 0)  # a job's history starts near 0
    last = history[-1][0] if history and history[-1][1] > 0 else job["submitted"]
    idle = _minutes(last, now)
    state = job.get("state", "?").removeprefix("JOB_STATE_").lower()
    name = "-".join(job["display"].split("-")[2:4])
    line = f"picture job {name}: {state} {done}/{total}, +{gained} in the last hour"
    line += f", last picture {_span(idle)} ago" if done else f", none yet after {_span(idle)}"
    if idle >= STALL_MINUTES and state in ("running", "pending"):
        line += f"; STALLED? no new picture for {_span(idle)}, Google may be throttling"
    return line


def progress_lines(running: list[dict[str, Any]], drawn: int, wanted: int,
                   now: datetime | None = None) -> list[str]:
    """What `full` prints each poll for pictures: a line per job and one for the whole run.

    `drawn` counts pictures on disk, `wanted` all of them. The pace is the running job's pictures
    over the time since it was submitted, so it is the pace of one lone job.
    """
    now = now or _now()
    lines = [job_progress(job, now) for job in running]
    total = f"pictures on disk: {drawn:,} of {wanted:,} ({100 * drawn // max(wanted, 1)}%)"
    job = running[0] if running else None
    hours = _minutes(job["submitted"], now) / 60 if job else 0
    done = int(job.get("done") or 0) if job else 0
    if job and done >= 10 and hours > 0:
        pace = done / hours
        left = wanted - drawn - done  # the job's pictures reach the disk only when it ends
        total += f"; this job draws about {pace:.0f} an hour, so the rest takes about {_span(int(left / pace * 60))}"
    elif job:
        total += "; pace not known yet"
    return lines + [total]


def resolve(args: argparse.Namespace, rows: dict[str, Any]) -> tuple[Any, dict[str, str] | None]:
    """The account to submit to: `--provider current`, `--project`, or a providers.local.json id."""
    if args.provider in (None, "current") or args.project or args.credentials:
        row, remembered = account(args.project, args.credentials)
        rows[row.id] = row
        run.say(f"account: Google Cloud project {remembered['project']}, credentials {Path(remembered['credentials']).name}")
        return row, remembered
    provider = args.provider
    if provider not in rows:
        sys.exit(f"No provider {provider!r} in providers.local.json; its ids are: {', '.join(rows)}, "
                 "or `--provider current` for the shell's current Google Cloud account")
    row = rows[provider]
    if row.reason():
        sys.exit(f"{provider} cannot be called from this machine: {row.reason()}.")
    return row, None


ARGON_STATE = run.OUT / "argon.json"
ARGON_LOG = run.OUT / "argon.jsonl"
# What an Argon request in flight holds back from the cap: its input plus its `maxOutputTokens`, at
# the batch price, an upper bound (`argon.RESERVE`, kept here so the ledger needs no import).
ARGON_RESERVE = 0.13


def spent_through(provider: str, state: dict[str, Any] | None = None) -> tuple[float, float]:
    """Dollars already spent through a provider (both call logs), and held back for what is in
    flight there (pictures and Argon requests), each at its upper bound."""
    spent = 0.0
    for path in (run.OUT / "draws.jsonl", ARGON_LOG):
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                entry = json.loads(line)
                if entry.get("provider") == provider and entry.get("costUsd"):
                    spent += entry["costUsd"]
    state = state if state is not None else load()
    flying = sum(len(job["requests"]) for job in state["jobs"]
                 if job["provider"] == provider and not job.get("harvested")) * PICTURE_RESERVE
    if ARGON_STATE.exists():
        text_jobs = json.loads(ARGON_STATE.read_text(encoding="utf-8")).get("jobs", [])
        flying += sum(len(job["requests"]) for job in text_jobs
                      if job["provider"] == provider and not job.get("harvested")) * ARGON_RESERVE
    return spent, flying


def allowance(row: Any, state: dict[str, Any] | None = None, cap: float | None = None) -> float:
    """Dollars that may still be submitted on this account: the cap in billing.local.json (or a
    lower `--cap`), less what was spent and what is in flight."""
    limit = float(billing()["cap"])
    if cap is not None:
        limit = min(limit, cap)
    spent, flying = spent_through(row.id, state)
    return max(0.0, limit - spent - flying)


def submit_pictures(row: Any, remembered: dict[str, str] | None, args: argparse.Namespace,
                    chosen: list[dict[str, Any]], state: dict[str, Any], prompts: dict[str, str],
                    dry_run: bool = False, max_jobs: int | None = None) -> list[dict[str, Any]]:
    """Submit the pictures still wanted that the cap allows, most popular first. The jobs made.

    `max_jobs` stops after that many jobs: Vertex serves about one picture job at a time and leaves
    the others at 0, so the full run keeps one in flight.
    """
    left = allowance(row, state, getattr(args, "cap", None))
    plan = _plan(args, chosen, state, left)
    unchecked = sum(1 for entry in chosen if not entry.get("checked"))
    groups: dict[str, int] = defaultdict(int)
    for group, _key in plan:
        groups[group] += 1
    if plan or dry_run:
        run.say(f"pictures to submit: {len(plan)}, holding ${len(plan) * PICTURE_RESERVE:.2f} of the "
                f"${left:.2f} the cap leaves; " + (", ".join(f"{g} {n}" for g, n in groups.items()) or "none")
                + (f"; {unchecked} scripts wait for the fact-check" if unchecked else ""))
    if dry_run or not plan:
        return []
    bucket = bucket_for(row)
    known = set(_list(row, bucket, "refs/"))
    made = []
    for job in _new_jobs(row, bucket, plan, args.job_size, state, remembered):
        if max_jobs is not None and len(made) >= max_jobs:
            break
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
        made.append(job)
        run.say(f"submitted {job['display']}: {len(job['requests'])} pictures")
    return made


def run_batch(args: argparse.Namespace) -> None:
    chosen = run.prepare(args)
    rows = _rows()
    row, remembered = resolve(args, rows)
    guard(row)
    state = load()
    prompts = run.prompts_for(chosen)

    running = _collect(state, rows)
    spent, flying = spent_through(row.id, state)
    run.say(f"cap ${float(billing()['cap']):.2f} on this account"
            + (f" (this run: ${args.cap:.2f})" if args.cap is not None else "")
            + f": ${spent:.2f} spent, ${flying:.2f} held for jobs in flight; "
            f"{sum(len(j['requests']) for j in running)} pictures in {len(running)} jobs already in flight")
    running += submit_pictures(row, remembered, args, chosen, state, prompts, dry_run=args.dry_run)
    if args.dry_run:
        return
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


def cancel(args: argparse.Namespace) -> None:
    """Cancel every picture job in flight. Only on the account billing.local.json names: the shell's
    current sign-in, checked by `guard`, and only jobs whose provider is that account and whose
    resource name carries its project number. Any other job in flight stops the command before a
    single cancel is sent. What a cancelled job drew is billed and kept: the next collect reads it."""
    row, remembered = account(None, None)
    run.say(f"account: Google Cloud project {remembered['project']}, credentials {Path(remembered['credentials']).name}")
    guard(row)
    bucket_for(row)  # learns the allowed project's number, read off its bucket
    number = _numbers[row.id]
    state = load()
    flying = [job for job in state["jobs"] if not job.get("harvested")]
    for job in flying:
        if job["provider"] != row.id or not (job.get("name") or "").startswith(f"projects/{number}/"):
            raise Stop(f"job {job['display']} in flight is not on the account {BILLING.name} names "
                       f"(provider {job['provider']}); nothing was cancelled")
    if not flying:
        run.say("no picture job in flight; nothing to cancel")
        return
    host = _endpoint(row)[0].split("/v1/")[0]
    for job in flying:
        refresh(row, job)
        state_name = job["state"].removeprefix("JOB_STATE_").lower()
        if job["state"] not in RUNNING or job["state"] == "JOB_STATE_CANCELLING":
            run.say(f"{job['display']}: {state_name}, {job.get('done', 0)}/{len(job['requests'])}; left as it is")
            continue
        if args.dry_run:
            run.say(f"{job['display']}: {state_name}, {job.get('done', 0)}/{len(job['requests'])}; would cancel")
            continue
        _request(row, "POST", f"{host}/v1/{job['name']}:cancel")
        refresh(row, job)
        save(state)
        run.say(f"{job['display']}: cancel asked ({job['state'].removeprefix('JOB_STATE_').lower()}), "
                f"{job.get('done', 0)} of {len(job['requests'])} drawn; the next collect keeps them")


def cancel_command(args: argparse.Namespace) -> None:
    try:
        cancel(args)
    except Stop as stop:
        print(f"STOPPED: {stop}", flush=True)
        sys.exit(1)


def main(args: argparse.Namespace) -> None:
    try:
        run_batch(args)
    except Stop as stop:
        print(f"STOPPED: {stop}", flush=True)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nStopped here. Jobs already submitted keep running at Google; run the same command "
              "again to collect them.", flush=True)

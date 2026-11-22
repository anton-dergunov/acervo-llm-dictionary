"""Vertex batch jobs for the concept pictures, on the one account `gcp.py` pins.

Copied from `experiments/character-pictures/batch.py`, the route its full run settled on after the
batch queue slowed down: Nano Banana 2.1 in Vertex `batchPredictionJobs`, one job in flight at a
time, 250 pictures a job, about one picture a minute (that README, "The full run"). Kept as it was
there:

- a request's failure is told apart as a reason to stop (a login, a malformed request, an account
  that cannot pay) or a reason to wait and ask again (`_request`);
- the bucket is created on first use, and every job is written to the state file before it is
  created and again as soon as it is, so a stop at any moment never submits a picture twice;
- a job created under any project number but the pinned one is cancelled at once and the run stops;
- a finished job's rows are sorted into a picture, a refusal, or a row the 24-hour limit never
  reached (`unfinished`, simply asked for again); the k-th answer for a concept fills its k-th wanted
  take, and a take already on disk is never written twice; the job's files are then deleted;
- each check prints the job's count, the last hour's gain and `STALLED?` after 90 minutes without a
  new picture (a note only: nothing is cancelled).

Cut: stroke references (a concept's picture is drawn from text alone), Flex, Argon, provider rows
and the shell-profile checks. The sign-in is `gcp.verify()`'s checked credentials, sent explicitly;
every `gs://` path goes through `gcp.check_gs`, every job name through `gcp.check_job`.

A row is matched back to its concept by its prompt, which the output echoes: every concept's
composed prompt is its own.
"""

from __future__ import annotations

import base64
import json
import urllib.parse
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import httpx

import gcp

MODEL = "gemini-nano-banana-2.1"
LOCATION = "global"
# Vertex list prices per million tokens at the standard tier, from the billing account's price list
# (experiments/character-pictures/run.py): input, text out (thinking included), picture out. A batch
# job is billed at half. Measured there: $0.0244 a picture on average.
PRICE_IN, PRICE_TEXT, PRICE_IMAGE = 1.50, 7.50, 30.0
BATCH = 0.5
PICTURE_RESERVE = 0.04   # what a picture in flight holds back from the cap, above the measured cost
STORAGE = "https://storage.googleapis.com"
TIMEOUT = 120.0
HISTORY = 50
STALL_MINUTES = 90
RUNNING = {"JOB_STATE_QUEUED", "JOB_STATE_PENDING", "JOB_STATE_RUNNING", "JOB_STATE_CANCELLING",
           "JOB_STATE_UPDATING", "JOB_STATE_PAUSED", "JOB_STATE_UNSPECIFIED"}
LOGIN_HINT = ("The Google login has expired. Run `gcloud auth application-default login` as the pinned "
              "account and save the file where experiments/starter-pictures/.env says, then rerun.")


class Stop(Exception):
    """A reason the whole run must stop: a login, a setting, an account that cannot pay."""


# ── signed-in requests ──────────────────────────────────────────────────────


def _headers() -> dict[str, str]:
    import google.auth.exceptions
    from google.auth.transport.requests import Request

    pin = gcp.verify()
    credentials = pin.credentials
    if not credentials.valid:
        try:
            credentials.refresh(Request())
        except google.auth.exceptions.RefreshError:
            raise Stop(LOGIN_HINT) from None
    return {"Authorization": f"Bearer {credentials.token}", "x-goog-user-project": pin.project}


def _scrubbed(text: str) -> str:
    """A message without the pinned project's id or number: the log is committed."""
    pin = gcp.verify()
    return str(text).replace(pin.project, "<project>").replace(pin.number, "<number>")


def _message(response: httpx.Response) -> str:
    try:
        payload = response.json()
        return str((payload.get("error") or {}).get("message") or payload)[:600]
    except ValueError:
        return response.text[:600]


def _request(method: str, url: str, timeout: float = TIMEOUT, **kwargs: Any) -> httpx.Response:
    """One call to a Google API, with the reasons to stop told apart from the reasons to wait."""
    headers = {**_headers(), **kwargs.pop("headers", {})}
    try:
        response = httpx.request(method, url, headers=headers, timeout=timeout, **kwargs)
    except httpx.HTTPError as error:
        raise ConnectionError(f"{method} {url.split('?')[0]}: {error}") from None
    if response.is_success or response.status_code == 404:
        return response
    message = _scrubbed(_message(response))
    lowered = message.lower()
    if "billing" in lowered or "credit" in lowered or "payment" in lowered:
        raise Stop(f"the pinned account cannot pay: {message}")
    if response.status_code in (401, 403):
        if "reauth" in lowered or "invalid_grant" in lowered or "expired" in lowered:
            raise Stop(LOGIN_HINT)
        raise Stop(f"refused ({response.status_code}): {message}")
    if response.status_code == 400:
        raise Stop(f"the request was refused as malformed: {message}")
    raise ConnectionError(f"{response.status_code}: {message}")


# ── Cloud Storage ───────────────────────────────────────────────────────────


def bucket() -> str:
    """The experiment's own bucket in the pinned project, created on first use. Nothing else is touched."""
    pin = gcp.verify()
    name = pin.bucket
    response = _request("GET", f"{STORAGE}/storage/v1/b/{name}")
    if response.status_code == 404:
        print(f"creating the bucket gs://{name} (location US) for the batch jobs' files", flush=True)
        response = _request("POST", f"{STORAGE}/storage/v1/b", params={"project": pin.project},
                            json={"name": name, "location": "US",
                                  "iamConfiguration": {"uniformBucketLevelAccess": {"enabled": True}}})
        if response.status_code == 404:
            raise Stop(f"could not create gs://{name}: the project was not found")
    number = str(response.json().get("projectNumber") or "")
    if number != pin.number:
        raise Stop(f"gs://{name} belongs to another project (number {number or 'unknown'})")
    return name


def _object_url(name: str) -> str:
    return f"{STORAGE}/storage/v1/b/{bucket_name()}/o/{urllib.parse.quote(name, safe='')}"


def bucket_name() -> str:
    return gcp.verify().bucket


def _upload(name: str, data: bytes, kind: str) -> None:
    gcp.check_gs(f"gs://{bucket_name()}/{name}")
    _request("POST", f"{STORAGE}/upload/storage/v1/b/{bucket_name()}/o",
             params={"uploadType": "media", "name": name}, content=data, headers={"Content-Type": kind})


def _list(prefix: str) -> list[str]:
    names, token = [], None
    while True:
        params = {"prefix": prefix, "fields": "items(name),nextPageToken"}
        if token:
            params["pageToken"] = token
        payload = _request("GET", f"{STORAGE}/storage/v1/b/{bucket_name()}/o", params=params).json()
        names += [item["name"] for item in payload.get("items") or []]
        token = payload.get("nextPageToken")
        if not token:
            return names


def _lines(name: str):
    """A JSONL object's lines, streamed: a job's output holds every picture, base64."""
    with httpx.stream("GET", _object_url(name), params={"alt": "media"}, headers=_headers(),
                      timeout=600.0) as response:
        if not response.is_success:
            raise ConnectionError(f"reading {name}: {response.status_code}")
        for line in response.iter_lines():
            if line.strip():
                yield line


def _delete(names: list[str]) -> None:
    for name in names:
        _request("DELETE", _object_url(name))


# ── batch jobs ──────────────────────────────────────────────────────────────


def _base() -> str:
    host = "aiplatform.googleapis.com" if LOCATION == "global" else f"{LOCATION}-aiplatform.googleapis.com"
    return f"https://{host}/v1/projects/{gcp.verify().project}/locations/{LOCATION}"


def _host() -> str:
    return _base().split("/v1/")[0]


def request_line(prompt: str) -> dict[str, Any]:
    """The request `call.image` sends for a picture, in the batch file's shape: a square 1K picture
    (the google-cloud family's `imageConfig`), from the prompt alone, with no seed."""
    return {"request": {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"responseModalities": ["IMAGE", "TEXT"],
                             "imageConfig": {"imageSize": "1K", "aspectRatio": "1:1"}},
    }}


def find_job(display: str) -> dict[str, Any] | None:
    payload = _request("GET", f"{_base()}/batchPredictionJobs",
                       params={"filter": f'display_name="{display}"'}).json()
    jobs = payload.get("batchPredictionJobs") or []
    return jobs[0] if jobs else None


def create_job(job: dict[str, Any], body: str) -> None:
    """Upload a job's requests and create it; the state is saved by the caller. A job created under
    any project number but the pinned one is cancelled at once and the run stops."""
    source = gcp.check_gs(f"gs://{bucket_name()}/{job['prefix']}/input.jsonl")
    destination = gcp.check_gs(f"gs://{bucket_name()}/{job['prefix']}/output")
    _upload(f"{job['prefix']}/input.jsonl", body.encode("utf-8"), "application/jsonl")
    created = _request("POST", f"{_base()}/batchPredictionJobs", json={
        "displayName": job["display"],
        "model": f"publishers/google/models/{MODEL}",
        "inputConfig": {"instancesFormat": "jsonl", "gcsSource": {"uris": [source]}},
        "outputConfig": {"predictionsFormat": "jsonl", "gcsDestination": {"outputUriPrefix": destination}},
    }).json()
    job["name"] = created["name"]
    job["state"] = created.get("state", "JOB_STATE_PENDING")
    try:
        gcp.check_job(job["name"])
    except gcp.Refused:
        _request("POST", f"{_host()}/v1/{job['name']}:cancel")
        raise Stop(f"job {job['display']} was created outside the pinned project; it was cancelled at once") from None


def refresh(job: dict[str, Any]) -> None:
    gcp.check_job(job["name"])
    response = _request("GET", f"{_host()}/v1/{job['name']}")
    if response.status_code == 404:
        job["state"], job["error"] = "JOB_STATE_FAILED", "the job no longer exists"
        return
    payload = response.json()
    job["state"] = payload.get("state", job.get("state"))
    stats = payload.get("completionStats") or {}
    job["done"] = int(stats.get("successfulCount") or 0)
    job["failed"] = int(stats.get("failedCount") or 0)
    history = job.setdefault("progress", [])
    if not history or history[-1][1] != job["done"]:
        history.append([now().isoformat(timespec="seconds"), job["done"]])
        del history[:-HISTORY]
    if payload.get("error"):
        job["error"] = _scrubbed(str(payload["error"].get("message") or payload["error"]))


def cancel(job: dict[str, Any]) -> None:
    gcp.check_job(job["name"])
    _request("POST", f"{_host()}/v1/{job['name']}:cancel")


def cost(usage: dict[str, Any]) -> float:
    """What one answer cost in a batch job (half the list price)."""
    if not usage:
        return PICTURE_RESERVE
    image = sum(int(d.get("tokenCount") or 0) for d in usage.get("candidatesTokensDetails") or []
                if d.get("modality") == "IMAGE")
    text = int(usage.get("candidatesTokenCount") or 0) - image + int(usage.get("thoughtsTokenCount") or 0)
    spent = (int(usage.get("promptTokenCount") or 0) * PRICE_IN + max(text, 0) * PRICE_TEXT
             + image * PRICE_IMAGE) / 1e6
    return round(spent * BATCH, 5)


def picture_of(line: dict[str, Any], job_error: str | None = None) -> tuple[str, Any]:
    """What one answer holds: ("image", bytes), ("refused", why) or ("unfinished", why). A row the
    model never answered (no candidate and no prompt feedback) is unfinished, not refused."""
    response = line.get("response") or {}
    candidate = (response.get("candidates") or [{}])[0]
    image = next((p["inlineData"] for p in (candidate.get("content") or {}).get("parts") or []
                  if "inlineData" in p and str(p["inlineData"].get("mimeType", "")).startswith("image/")), None)
    if not image and not candidate and not response.get("promptFeedback"):
        return "unfinished", line.get("status") or job_error or "the job ended before this row ran"
    if not image:
        said = " ".join(p.get("text", "") for p in (candidate.get("content") or {}).get("parts") or [])
        reason = (line.get("status") or candidate.get("finishReason")
                  or (response.get("promptFeedback") or {}).get("blockReason") or "no image")
        return "refused", f"{reason}: {said}".strip()
    return "image", base64.b64decode(image["data"])


def harvest(job: dict[str, Any], prompts: dict[str, str],
            write: Callable[[str, int, bytes, dict[str, Any]], bool],
            log: Callable[[dict[str, Any]], None]) -> tuple[int, int, int]:
    """Write every picture a finished job drew; a refusal or a row never reached is logged and left
    missing. (drawn, refused, unfinished).

    `prompts` maps each concept to the prompt the job sent for it; `write(concept, take, data, usage)`
    stores one picture and says False when that take is already on disk.
    """
    concept_of = {text: concept for concept, text in prompts.items()}
    wanted: dict[str, list[int]] = defaultdict(list)
    for key in job["requests"]:
        concept, take = key.rsplit("/", 1)
        wanted[concept].append(int(take))
    seen: dict[str, int] = defaultdict(int)
    drawn = refused = unfinished = 0
    names = _list(f"{job['prefix']}/output")
    for name in sorted(n for n in names if n.endswith(".jsonl")):
        for raw in _lines(name):
            line = json.loads(raw)
            parts = (((line.get("request") or {}).get("contents") or [{}])[0].get("parts")) or []
            text = next((p.get("text") for p in parts if "text" in p), "")
            concept = concept_of.get(text)
            if concept not in wanted:
                continue
            index = seen[concept]
            seen[concept] += 1
            if index >= len(wanted[concept]):
                continue
            take = wanted[concept][index]
            entry = {"at": now().isoformat(timespec="seconds"), "concept": concept, "take": take,
                     "job": job["display"], "model": MODEL, "route": "vertex-batch"}
            kind, found = picture_of(line, job.get("error"))
            if kind != "image":
                log({**entry, "error": kind, "message": _scrubbed(found)})
                if kind == "refused":
                    refused += 1
                else:
                    unfinished += 1
                continue
            usage = (line.get("response") or {}).get("usageMetadata") or {}
            if write(concept, take, found, usage):
                drawn += 1
    job["harvested"] = True
    job["drawn"], job["refused"], job["unfinished"] = drawn, refused, unfinished
    _delete(names + [f"{job['prefix']}/input.jsonl"])
    return drawn, refused, unfinished


# ── progress ────────────────────────────────────────────────────────────────


def now() -> datetime:
    return datetime.now(timezone.utc)


def minutes(since: str, at: datetime) -> int:
    return max(0, int((at - datetime.fromisoformat(since)).total_seconds() // 60))


def span(count: int) -> str:
    if count < 90:
        return f"{count} min"
    if count < 48 * 60:
        return f"{count / 60:.1f} h"
    return f"{count / 1440:.1f} d"


def job_progress(job: dict[str, Any], at: datetime | None = None) -> str:
    """One line on a running job: how far it is, the last hour, how long since a picture."""
    at = at or now()
    done, total = int(job.get("done") or 0), len(job["requests"])
    history = job.get("progress") or []
    hour_ago = [count for when, count in history if minutes(when, at) >= 60]
    gained = done - (hour_ago[-1] if hour_ago else 0)
    last = history[-1][0] if history and history[-1][1] > 0 else job["submitted"]
    idle = minutes(last, at)
    state = job.get("state", "?").removeprefix("JOB_STATE_").lower()
    line = f"job {job['display']}: {state} {done}/{total}, +{gained} in the last hour"
    line += f", last picture {span(idle)} ago" if done else f", none yet after {span(idle)}"
    if idle >= STALL_MINUTES and state in ("running", "pending"):
        line += f"; STALLED? no new picture for {span(idle)}, Google may be throttling"
    return line


# ── state ───────────────────────────────────────────────────────────────────


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"jobs": []}


def save(state: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    temporary.replace(path)

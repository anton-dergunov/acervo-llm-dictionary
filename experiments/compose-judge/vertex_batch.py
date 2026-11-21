"""Vertex AI batch jobs for Gemini: submit a JSONL of requests, wait, download.

Adapted from the owner's `task-concept-retrieval/tcr/vertex_batch.py`. A run's state lives in
`runs/<run>/state.json`, so a submitted job is never resubmitted and `wait` / `collect` resume from any
later session. Batch input and output sit in the pinned project's private bucket (`gcp.py`).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import gcp

ENDED = {"JOB_STATE_SUCCEEDED", "JOB_STATE_FAILED", "JOB_STATE_CANCELLED", "JOB_STATE_EXPIRED",
         "JOB_STATE_PARTIALLY_SUCCEEDED"}
BUCKET_LOCATION = "us-central1"   # a bucket needs a real region; global jobs read it fine
# gemini-4-argon is served on the global endpoint only (us-central1 answers 404).
LOCATION = os.environ.get("VERTEX_BATCH_LOCATION", "global")

_CLIENT = None


def client():
    """One client for the process, on the pinned credentials only."""
    global _CLIENT
    if _CLIENT is None:
        from google import genai
        pin = gcp.verify()
        _CLIENT = genai.Client(vertexai=True, project=pin.project, location=LOCATION, credentials=pin.credentials)
    return _CLIENT


def log(message: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {message}", flush=True)


def gcloud(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    """gcloud as the pinned account and project, on gs:// paths in the pinned bucket only."""
    flags = gcp.gcloud_flags()
    for arg in args:
        gcp.check_gs(str(arg))
    env = {**os.environ, "CLOUDSDK_ACTIVE_CONFIG_NAME": gcp.verify().gcloud_config}
    return subprocess.run(["gcloud", *args, *flags], capture_output=True, text=True, check=check, env=env)


def request_json(system: str, user: str, thinking: str | None, temperature: float = 1.0) -> dict[str, Any]:
    """The REST body of one generateContent request. JSON mode, never a schema (AGENTS.md: no
    constrained decoding anywhere without a measurement)."""
    config: dict[str, Any] = {"temperature": temperature, "responseMimeType": "application/json"}
    if thinking:
        config["thinkingConfig"] = {"thinkingLevel": thinking.upper()}
    return {"contents": [{"role": "user", "parts": [{"text": user}]}],
            "systemInstruction": {"parts": [{"text": system}]},
            "generationConfig": config}


def response_text(response: dict[str, Any]) -> str:
    # A candidate ending MALFORMED_RESPONSE carries no parts; its articles are asked again.
    parts = response["candidates"][0].get("content", {}).get("parts", [])
    return "".join(part.get("text", "") for part in parts if not part.get("thought"))


def usage_of(response: dict[str, Any]) -> dict[str, int]:
    usage = response.get("usageMetadata", {})
    return {"prompt": usage.get("promptTokenCount", 0), "output": usage.get("candidatesTokenCount", 0),
            "thoughts": usage.get("thoughtsTokenCount", 0), "cached": usage.get("cachedContentTokenCount", 0)}


class Run:
    """One batch round: `runs/<run>/<round>/{input.jsonl, state.json, output/}`."""

    def __init__(self, folder: Path, model: str):
        self.dir = folder
        self.dir.mkdir(parents=True, exist_ok=True)
        self.model = model

    @property
    def input(self) -> Path:
        return self.dir / "input.jsonl"

    def state(self) -> dict[str, Any]:
        path = self.dir / "state.json"
        return json.loads(path.read_text()) if path.exists() else {}

    def save_state(self, state: dict[str, Any]) -> None:
        (self.dir / "state.json").write_text(json.dumps(state, indent=1))

    def submit(self, display_name: str) -> None:
        state = self.state()
        if state.get("job"):
            log(f"already submitted: {state['job']}; not resubmitting")
            return
        if not self.input.exists():
            sys.exit("no input.jsonl: prepare the round first")
        bucket = gcp.verify().bucket
        ensure_bucket(bucket)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        prefix = f"gs://{bucket}/judge/{self.dir.parent.name}-{self.dir.name}-{stamp}"
        log(f"uploading input to {prefix}/input.jsonl")
        gcloud("storage", "cp", str(self.input), f"{prefix}/input.jsonl")
        from google.genai import types
        job = client().batches.create(model=self.model, src=f"{prefix}/input.jsonl",
                                      config=types.CreateBatchJobConfig(dest=f"{prefix}/output",
                                                                        display_name=display_name))
        gcp.check_job(job.name)
        state.update(job=job.name, prefix=prefix, submitted=stamp, location=LOCATION)
        self.save_state(state)
        log(f"submitted {job.name} ({job.state})")

    def job(self):
        state = self.state()
        if not state.get("job"):
            sys.exit("nothing submitted for this round")
        return client().batches.get(name=gcp.check_job(state["job"]))

    def wait(self, poll: int):
        while True:
            job = self.job()
            log(describe_job(job))
            if ended(job):
                return job
            time.sleep(poll)

    def download(self) -> Iterator[dict[str, Any]]:
        """Download the job's output; yield every output record (request + response)."""
        state = self.state()
        out = self.dir / "output"
        out.mkdir(exist_ok=True)
        log(f"downloading {state['prefix']}/output")
        gcloud("storage", "cp", "-r", f"{state['prefix']}/output/*", str(out))
        for path in sorted(out.rglob("*.jsonl")):
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    yield json.loads(line)


def ensure_bucket(bucket: str) -> None:
    if gcloud("storage", "buckets", "describe", f"gs://{bucket}", check=False).returncode == 0:
        return
    log(f"creating bucket gs://{bucket} in {BUCKET_LOCATION}")
    gcloud("storage", "buckets", "create", f"gs://{bucket}", f"--location={BUCKET_LOCATION}",
           "--uniform-bucket-level-access", "--public-access-prevention")


def describe_job(job) -> str:
    stats = job.completion_stats
    counts = (f"ok {stats.successful_count}, failed {stats.failed_count}, incomplete {stats.incomplete_count}"
              if stats else "no counts yet")
    error = f" error: {job.error}" if job.error else ""
    return f"{job.state} ({counts}){error}"


def ended(job) -> bool:
    return str(job.state).split(".")[-1] in ENDED

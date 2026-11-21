"""Vertex AI runs only on the Google account and project pinned in this directory's `.env`.

Adapted from the owner's `task-concept-retrieval/tcr/gcp.py`. Every Vertex call the judge makes
(`judge.py`'s online pilot, `vertex_batch.py`) calls `verify()` first, once per process. It stops the
process, before anything is sent, unless all of these agree:

- `.env`'s VERTEX_ACCOUNT, VERTEX_PROJECT, GOOGLE_APPLICATION_CREDENTIALS (an ADC file) and
  CLOUDSDK_ACTIVE_CONFIG_NAME (a gcloud configuration), with no shell variable overriding them;
- the ADC file's account, as Google's tokeninfo reports it, and its quota project;
- the gcloud configuration's account and project.

The checked credentials go to the genai client explicitly, so no other ADC source is used; gcloud
always gets --account and --project; batch files must live in gs://<project>-judge-batch and batch
jobs must belong to the project's number. The account and project live only in the gitignored
`.env`, never in code, because this repository is public. `judge.py check` runs the checks and
prints them.
"""

from __future__ import annotations

import functools
import os
import subprocess
from pathlib import Path
from typing import NamedTuple

HERE = Path(__file__).resolve().parent
ENV_FILE = HERE / ".env"
KEYS = ("VERTEX_ACCOUNT", "VERTEX_PROJECT", "GOOGLE_APPLICATION_CREDENTIALS", "CLOUDSDK_ACTIVE_CONFIG_NAME")
TOKENINFO = "https://oauth2.googleapis.com/tokeninfo"
BUCKET_SUFFIX = "-judge-batch"


class Refused(SystemExit):
    def __init__(self, why: str):
        super().__init__(f"GCP guard (experiments/compose-judge/gcp.py): {why}\n"
                         f"Nothing was sent to Google Cloud.")


class Pin(NamedTuple):
    account: str
    project: str
    number: str          # the project's number, the prefix of its batch job names
    adc: str
    gcloud_config: str
    bucket: str
    credentials: object  # google.auth credentials, checked


def _env_file() -> dict:
    from dotenv import dotenv_values
    if not ENV_FILE.is_file():
        raise Refused(f"no {ENV_FILE.name} beside gcp.py; copy .env.example and fill it in.")
    return dict(dotenv_values(ENV_FILE))


def pinned(file: dict | None = None) -> dict:
    """The pin from `.env`, checked against the shell; no network. Puts the pin in os.environ."""
    file = _env_file() if file is None else file
    missing = [k for k in KEYS if not file.get(k)]
    if missing:
        raise Refused(f".env lacks {', '.join(missing)}; Vertex needs an explicit pin.")
    account, project = file["VERTEX_ACCOUNT"], file["VERTEX_PROJECT"]
    expected = {k: file[k] for k in KEYS}
    # Variables that would redirect gcloud or a client if set in the shell.
    expected.update({"GOOGLE_CLOUD_PROJECT": project, "CLOUDSDK_CORE_PROJECT": project,
                     "CLOUDSDK_CORE_ACCOUNT": account})
    for key, want in expected.items():
        have = os.environ.get(key)
        if have is not None and have != want:
            raise Refused(f"{key} is {have!r} in the environment but .env pins {want!r}; "
                          f"unset it (`unset {key}`) or fix .env.")
    adc = os.path.expanduser(file["GOOGLE_APPLICATION_CREDENTIALS"])
    if not Path(adc).is_file():
        raise Refused(f"no ADC file at {adc}.")
    os.environ.update({**{k: file[k] for k in KEYS}, "GOOGLE_APPLICATION_CREDENTIALS": adc})
    return {"account": account, "project": project, "adc": adc,
            "gcloud_config": file["CLOUDSDK_ACTIVE_CONFIG_NAME"], "bucket": f"{project}{BUCKET_SUFFIX}"}


def _tokeninfo(token: str) -> dict:
    import requests
    response = requests.get(TOKENINFO, params={"access_token": token}, timeout=30)
    response.raise_for_status()
    return response.json()


def _credentials(adc: str, account: str, project: str):
    import google.auth
    from google.auth.transport.requests import Request
    credentials, _ = google.auth.load_credentials_from_file(adc)
    quota = getattr(credentials, "quota_project_id", None)
    if quota != project:
        raise Refused(f"the ADC file {adc} bills quota project {quota!r}, not {project!r}.")
    try:
        credentials.refresh(Request())
        email = _tokeninfo(credentials.token).get("email")
    except Exception as error:  # noqa: BLE001
        raise Refused(f"could not confirm the ADC file's account ({error}); run "
                      f"`gcloud auth application-default login --account {account}` "
                      f"and save the file to {adc}.") from error
    if email != account:
        raise Refused(f"the ADC file {adc} belongs to {email!r}, not the pinned {account!r}.")
    return credentials


def _gcloud(args: list[str], gcloud_config: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "CLOUDSDK_ACTIVE_CONFIG_NAME": gcloud_config}
    return subprocess.run(["gcloud", *args], capture_output=True, text=True, env=env)


def _check_gcloud(account: str, project: str, gcloud_config: str) -> str:
    """The gcloud configuration's account and project; returns the project number."""
    for prop, want in (("account", account), ("project", project)):
        have = _gcloud(["config", "get", prop], gcloud_config).stdout.strip()
        if have != want:
            raise Refused(f"gcloud configuration {gcloud_config!r} has {prop} {have!r}, not {want!r}.")
    result = _gcloud(["projects", "describe", project, f"--account={account}",
                      "--format=value(projectNumber)"], gcloud_config)
    number = result.stdout.strip()
    if result.returncode or not number.isdigit():
        raise Refused(f"cannot read project {project}'s number as {account}: {result.stderr.strip()[-300:]}")
    return number


@functools.lru_cache(maxsize=None)
def verify() -> Pin:
    pin = pinned()
    credentials = _credentials(pin["adc"], pin["account"], pin["project"])
    number = _check_gcloud(pin["account"], pin["project"], pin["gcloud_config"])
    return Pin(pin["account"], pin["project"], number, pin["adc"], pin["gcloud_config"], pin["bucket"],
               credentials)


def gcloud_flags() -> list[str]:
    pin = verify()
    return [f"--account={pin.account}", f"--project={pin.project}"]


def check_gs(path: str) -> str:
    """A gs:// path must lie in the pinned project's bucket."""
    bucket = verify().bucket
    if path.startswith("gs://") and not (path == f"gs://{bucket}" or path.startswith(f"gs://{bucket}/")):
        raise Refused(f"{path} is outside the pinned bucket gs://{bucket}.")
    return path


def check_job(name: str) -> str:
    """A batch job name must belong to the pinned project (projects/<number>/…)."""
    number = verify().number
    if not name.startswith(f"projects/{number}/"):
        raise Refused(f"batch job {name} is not in project {verify().project} (number {number}).")
    return name

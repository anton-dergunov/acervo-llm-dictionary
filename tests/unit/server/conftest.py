"""One real service per test, over a temporary SQLite file.

There is no fake application here on purpose. The harness this replaces stubbed PocketBase's globals
and stood in for the save hook, which meant several of its assertions were about the stub; against a
real service with a throwaway database the same tests are about the thing that ships.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from litellm import ModelResponse
from fastapi.testclient import TestClient

from acervo.domain import SCHEMA_VERSION

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
PROMPTS = REPOSITORY_ROOT / "prompts"

OWNER_EMAIL = "learner@account.example.com"
OWNER_PASSWORD = "correct-horse-battery"
DEVICE = "device000000001"


@dataclass
class ModelStub:
    """Stands in for LiteLLM, and records what it was asked.

    It tells the two capture calls apart the way the real prompts do — by the opening line of
    `prompts/acervo_resolve.md` — so a test that changes one call's answer cannot silently change
    the other's. That line now arrives as the system message rather than inside Google's
    `systemInstruction`, which is the only thing about this that moved.

    Failures are raised as **real LiteLLM exceptions**. Raising Acervo's own `ProviderRefused`
    instead would skip `acervo.models.call.classify` entirely — and that function is what decides
    whether the file ingestion retries, so a test suite that stubbed past it would be asserting
    nothing about the contract it exists to protect.
    """

    resolution: dict[str, Any] = field(default_factory=dict)
    article: dict[str, Any] = field(default_factory=dict)
    # The image brief writer, which is told apart by carrying no system message at all: capture
    # puts its instructions there and the brief writer puts the whole template in the user turn.
    brief: dict[str, Any] = field(default_factory=dict)
    # The clip selector, which also puts its template in the user turn — so these two are told apart
    # by the opening line of the template itself, the way the two capture calls already are.
    selection: dict[str, Any] = field(default_factory=dict)
    # The two chat prompts, told apart from each other and from capture by their opening lines, the
    # way the two capture calls already are. Two answers rather than one because a reference subject
    # returns a `capture` where an article subject returns a `proposal`, and a test that could only
    # set one would be unable to assert that each kind drops the other's field.
    chat: dict[str, Any] = field(default_factory=dict)
    chat_reference: dict[str, Any] = field(default_factory=dict)
    calls: list[dict[str, Any]] = field(default_factory=list)
    error: BaseException | None = None
    errors: list[BaseException | None] = field(default_factory=list)
    # Models that always refuse, by model id. A positional script cannot express a capture any more:
    # a rate-limited pair rests, so the second of the two model calls skips what the first exhausted
    # and the failures no longer land on fixed positions.
    limited: set[str] = field(default_factory=set)
    text: str | None = None
    reasoning: str | None = None

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs["model"] in self.limited:
            import litellm

            raise litellm.RateLimitError(
                message="provider details that must stay private",
                llm_provider="stub", model=kwargs["model"],
            )
        failure = self.errors.pop(0) if self.errors else self.error
        if failure is not None:
            raise failure
        if self.text is not None:
            body = self.text
        else:
            system = next(
                (m["content"] for m in kwargs["messages"] if m["role"] == "system"), None
            )
            if system is None:
                asked = next(
                    (m["content"] for m in kwargs["messages"] if m["role"] == "user"), ""
                )
                body = _dumped(
                    self.selection if "You choose recorded speech" in asked else self.brief
                )
            elif "You decide what a learner" in system:
                body = _dumped(self.resolution)
            elif "You answer a learner's message" in system:
                body = _dumped(self.chat)
            elif "You help a learner read" in system:
                body = _dumped(self.chat_reference)
            else:
                body = _dumped(self.article)
        answered = ModelResponse(
            model=kwargs["model"],
            choices=[
                {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": body}}
            ],
        )
        if self.reasoning is not None:
            answered.choices[0].message.reasoning_content = self.reasoning
        return answered


def _dumped(answer: Any) -> str:
    return answer if isinstance(answer, str) else json.dumps(answer)


# A real 2x2 PNG, so the encoder in `images/render.py` runs for real rather than being stubbed past.
# The WebP that comes out is what the media route then serves, which is the thing worth asserting.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAF0lEQVQIHWNkYPjPgAQYkdhgJlSAgQEA"
    "HqQCAQ0QzWkAAAAASUVORK5CYII="
)

# A second picture, different bytes, for the tests about redrawing. A picture's reference carries a
# digest of what it holds, so a stub that always draws the same thing would make every "the
# reference changed" assertion pass while proving nothing.
PNG_OTHER = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAEklEQVR4nGM8IRfFwMDAxAAGAA+YAURp"
    "O7lOAAAAAElFTkSuQmCC"
)


@dataclass
class ImageStub:
    """Stands in for LiteLLM's image call, and records what it was asked.

    Failures are raised as real LiteLLM exceptions for `ModelStub`'s reason: `models.call.classify`
    is what decides whether a refusal is terminal or whether the chain moves on, and a stub that
    raised Acervo's own exception would skip the function the tests exist to pin.
    """

    data: bytes | None = PNG
    calls: list[dict[str, Any]] = field(default_factory=list)
    error: BaseException | None = None

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        encoded = base64.b64encode(self.data).decode() if self.data else None
        return SimpleNamespace(data=[SimpleNamespace(b64_json=encoded)], usage=None)


@dataclass
class Server:
    client: TestClient
    owner: str
    token: str
    settings: Any
    model: ModelStub
    painter: ImageStub
    downloads: Path
    dictionaries: Path
    media: Path
    web: Path

    @property
    def auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def api(self) -> Any:
        """An `AcervoClient` pointed at this application rather than at a socket.

        What a job or a script would hold, over the same routes, so a write path is exercised as it
        actually runs rather than through a second code path built for tests.
        """
        from acervo.client import AcervoClient

        client = AcervoClient(str(self.client.base_url), http=self.client)
        client.token = self.token
        return client

    def get(self, path: str, **kwargs):
        return self.client.get(f"/api/acervo/v1{path}", headers=self.auth, **kwargs)

    def post(self, path: str, body: dict, **kwargs):
        return self.client.post(f"/api/acervo/v1{path}", headers=self.auth, json=body, **kwargs)

    def put(self, path: str, body: dict, **kwargs):
        return self.client.put(f"/api/acervo/v1{path}", headers=self.auth, json=body, **kwargs)

    def delete(self, path: str, **kwargs):
        """The device rides in a header, because a DELETE has no body to put it in."""
        headers = {**self.auth, "X-Acervo-Device": DEVICE, **kwargs.pop("headers", {})}
        return self.client.delete(f"/api/acervo/v1{path}", headers=headers, **kwargs)

    def send(self, path: str, payload: bytes, drawn_by: str = "", **kwargs):
        """A raw body, which is how a picture arrives — no multipart, one part.

        `drawn_by` names the model that drew it, which is what tells a *restore* from a picture the
        owner chose.
        """
        headers = {**self.auth, "Content-Type": "image/png", "X-Acervo-Device": DEVICE}
        if drawn_by:
            headers["X-Acervo-Drawn-By"] = drawn_by
        return self.client.put(f"/api/acervo/v1{path}", headers=headers, content=payload, **kwargs)

    def push(self, changes: dict, device: str = DEVICE):
        return self.post("/graph", {"schemaVersion": SCHEMA_VERSION, "deviceId": device, "changes": changes})

    def pull(self, since: int = 0):
        return self.get(f"/graph?schemaVersion={SCHEMA_VERSION}&since={since}")

    def capture(self, **overrides):
        body = {
            "schemaVersion": SCHEMA_VERSION,
            "deviceId": DEVICE,
            "mode": "single",
            "text": "some text",
            **overrides,
        }
        return self.post("/capture", body)

    def chat(self, **overrides):
        body = {
            "schemaVersion": SCHEMA_VERSION,
            "deviceId": DEVICE,
            "subject": {
                "kind": "article",
                "lexemeId": "lexemepicar0001",
                "document": "headword: picar\nlanguage: es\n",
                "focus": None,
            },
            "turns": [{"role": "you", "text": "what does this mean?"}],
            **overrides,
        }
        return self.post("/chat", body)


@pytest.fixture(autouse=True)
def no_remembered_refusals():
    """A refused provider rests for a while, in process memory. Each test gets a fresh process's
    worth of that, or one test's 429 would reorder the next test's chain."""
    from acervo.models.cooldown import rests

    rests.forget_all()
    yield
    rests.forget_all()


@pytest.fixture(autouse=True)
def no_lane_windows(monkeypatch):
    """The lanes' calls-a-minute windows run on real time, and a test draws four pictures in a
    millisecond — so every picture after the first would wait out a real minute. The window is what
    `test_jobs.py` pins on purpose; everywhere else it would only turn each test into a test of it."""
    from acervo.work import retry

    monkeypatch.setitem(retry.LANES, "image", 0)


@pytest.fixture
def server(tmp_path, monkeypatch) -> Server:
    downloads = tmp_path / "downloads"
    dictionaries = tmp_path / "dictionaries"
    media = tmp_path / "media"
    web = tmp_path / "web"
    for directory in (downloads, dictionaries, media, web):
        directory.mkdir()

    monkeypatch.setenv("ACERVO_DB_PATH", str(tmp_path / "acervo.db"))
    monkeypatch.setenv("ACERVO_WEB_PATH", str(web))
    monkeypatch.setenv("ACERVO_DOWNLOADS_PATH", str(downloads))
    monkeypatch.setenv("ACERVO_DICTIONARIES_PATH", str(dictionaries))
    monkeypatch.setenv("ACERVO_MEDIA_PATH", str(media))
    monkeypatch.setenv("ACERVO_PROMPTS_PATH", str(PROMPTS))
    monkeypatch.setenv("ACERVO_APP_VERSION", "1.4.2")
    monkeypatch.setenv("ACERVO_APP_BUILD", "218")
    monkeypatch.setenv("ACERVO_JWT_SECRET", "test-secret")

    # One credentialed row, so the default chain is exactly `gemini-free` and a test about how a
    # refusal is classified is not also a test about falling through to somebody else. The tests
    # that are about the chain set these themselves.
    monkeypatch.setenv("GEMINI_API_KEY", "stub-key")
    monkeypatch.delenv("ACERVO_TEXT_CHAIN", raising=False)
    for name in (
        "CLOUDFLARE_API_TOKEN",
        "CLOUDFLARE_ACCOUNT_ID",
        "OPENAI_API_KEY",
        "OPENROUTER_API_KEY",
        "ACERVO_OLLAMA_URL",
        "ACERVO_VERTEX_PROJECT",
    ):
        monkeypatch.delenv(name, raising=False)

    from acervo.api.app import create_app
    from acervo.models import call as model_call
    from acervo.repository import accounts
    from acervo.services import prompts

    prompts.forget_prompts()
    model = ModelStub()
    painter = ImageStub()
    monkeypatch.setattr(model_call, "completion", model)
    monkeypatch.setattr(model_call, "image_generation", painter)

    app = create_app()
    client = TestClient(app, raise_server_exceptions=False)
    created = accounts.create(OWNER_EMAIL, OWNER_PASSWORD)
    signed_in = client.post(
        "/api/acervo/v1/session", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}
    ).json()["data"]

    return Server(
        client=client,
        owner=created["id"],
        token=signed_in["token"],
        settings=app.state.settings,
        model=model,
        painter=painter,
        downloads=downloads,
        dictionaries=dictionaries,
        media=media,
        web=web,
    )


@pytest.fixture
def other(server) -> Server:
    """A second account on the same server, for the cross-owner rules."""
    from acervo.repository import accounts

    email = "second@account.example.com"
    created = accounts.create(email, OWNER_PASSWORD)
    signed_in = server.client.post(
        "/api/acervo/v1/session", json={"email": email, "password": OWNER_PASSWORD}
    ).json()["data"]
    return Server(
        client=server.client,
        owner=created["id"],
        token=signed_in["token"],
        settings=server.settings,
        model=server.model,
        painter=server.painter,
        downloads=server.downloads,
        dictionaries=server.dictionaries,
        media=server.media,
        web=server.web,
    )

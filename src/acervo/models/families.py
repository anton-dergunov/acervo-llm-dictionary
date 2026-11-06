"""The families: the code that speaks to a provider, and every fact about one found the hard way.

A provider is a row the owner adds — one account, one credential — and its `family` names the entry
here that knows how to reach it. A family carries what a user should never have to know: the route
LiteLLM takes, the base URL, whether JSON mode is native, which parameter a provider refuses and
which it needs, how long it is worth waiting, where its usage page is. A family is code rather than
data because those facts were each discovered by a call that failed, and each is a fact about the
provider rather than about anybody's account.

What changes with the provider's own catalogue — its models and its voices — is *not* here: a family
asks the provider for those (`listing.py`), and only where a provider cannot list them does the owner
type them in.

Several families share one piece of code. Every OpenAI-compatible text service is the same LiteLLM
call with a different prefix, base URL and listing endpoint, so each is a preset: one entry here, no
code of its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

KINDS = ("text", "image", "audio", "ocr")
# `ocr` is reading the text on a photo, with where each word is. Its own kind rather than a use of
# `text`, because the answer is geometry and no language model gives geometry a reader can trust.

# Whether a family understands a request for JSON *mode* — `{"type": "json_object"}`, meaning "answer
# with a JSON object" and nothing more. Not a schema: this package does not send schemas at all
# (`docs/architecture/models.md`, "Constrained decoding is not used, anywhere"). `native` sends the
# request; `prompt` leaves the asking to the prompt. The reply is parsed by the caller either way.
JSON_MODES = ("native", "prompt")

# How a family is signed in to. `key` needs one; `key-or-file` takes a key or a credentials file;
# `optional` takes a key when the service wants one; `none` takes nothing.
CREDENTIALS = ("key", "key-or-file", "optional", "none")

# The groups "Add a provider" shows, in order.
GROUPS = ("Free to start", "Popular", "On your own machines", "Any compatible service")

# The speech order that exists to carry a direction, and so may hold only models that take one.
EXPRESSIVE_CHAIN = "audioExpressive"

_EMPTY: Mapping[str, Any] = MappingProxyType({})


@dataclass(frozen=True)
class Field:
    """One non-secret value a family asks for: an account id, a project, a base URL.

    `needed` says when it must be filled in — `always`, only with a credentials `file`, or `never`.
    `choices` makes it a pick rather than free text.
    """

    name: str
    label: str
    needed: str = "always"
    default: str | None = None
    hint: str | None = None
    choices: tuple[str, ...] = ()


@dataclass(frozen=True)
class Route:
    """How one kind is reached: through LiteLLM with a provider prefix, or by an adapter here.

    `file_only` is a kind only a credentials file reaches — Vertex, through Google Cloud — and
    `vertex` says LiteLLM is handed that file, its project and its location rather than a key.
    """

    via: str
    prefix: str = ""
    file_only: bool = False
    vertex: bool = False


@dataclass(frozen=True)
class Family:
    id: str
    label: str
    group: str
    hint: str
    routes: Mapping[str, Route]
    credential: str = "key"
    key_label: str = "API key"
    # Where the owner creates a key, and where they read their own usage and bill. Templates over
    # the provider's settings, never over its key.
    key_url: str | None = None
    usage_url: str | None = None
    # Where the owner reads a model's voices, for a provider that cannot list them and so has them
    # typed in.
    voices_url: str | None = None
    fields: tuple[Field, ...] = ()
    # The base URL LiteLLM is given, a template over the settings. None means LiteLLM's own default
    # for the prefix.
    base_url: str | None = None
    json_mode: str = "prompt"
    # Per-kind call parameters a provider needs, spread into the call after the caller's own wishes
    # so they win: a value here is here because the provider refused something without it.
    params: Mapping[str, Mapping[str, Any]] = _EMPTY
    # How long to wait on this family, per kind, when the caller does not insist. A family rather
    # than a constant because the spread is real: the same clip-selection call answers in 0.9-1.8 s
    # on the free Gemini tier and takes 21-37 s on Vertex.
    timeouts: Mapping[str, float] = _EMPTY
    # What the image route does with the parameters it is sent (see `call.image`).
    image: Mapping[str, Any] = _EMPTY
    # What the speech route needs: `inputField`, `encoding`, and `wire`, the provider's own spelling
    # of a locale where it differs (`cmn-CN` for `zh-Hans-CN`).
    audio: Mapping[str, Any] = _EMPTY
    # Which listing code asks this provider for its models and checks its key (`listing.py`), and
    # the base it asks when that differs from `base_url`.
    lister: str = "openai"
    list_url: str | None = None
    # A route that says whether a key works when the model list does not — OpenRouter lists its
    # models to anyone.
    check_url: str | None = None

    def serves(self, kind: str) -> bool:
        return kind in self.routes

    def field(self, name: str) -> Field | None:
        return next((one for one in self.fields if one.name == name), None)


def _frozen(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType({key: (MappingProxyType(dict(inner)) if isinstance(inner, Mapping) else inner)
                             for key, inner in value.items()})


def _text(prefix: str) -> Mapping[str, Route]:
    return MappingProxyType({"text": Route("litellm", prefix)})


_BASE_URL = Field("baseUrl", "Address", hint="Where the service answers")


FAMILIES: tuple[Family, ...] = (
    # ── free to start ──
    Family(
        # Two Flash-Lite models at 500 requests a day each, which is why a provider holds several
        # models per kind: they are separate buckets, and the second is reached by the first one's
        # 429. Temperature is deliberately unset: LiteLLM recommends leaving Gemini 3+ at its
        # default. Speech goes through the Interactions API (`gemini_tts.py`), not LiteLLM: reached
        # through LiteLLM a Gemini voice drops its direction before the request is built. The free
        # tier's speech is three requests a minute per model (measured on Flash-Lite TTS,
        # 6 Nov 2026), and the 429 says when to come back, which the cooldown reads.
        id="gemini-api", label="Gemini API", group="Free to start",
        hint="Text, and voices that take a direction",
        routes=MappingProxyType({
            "text": Route("litellm", "gemini/"),
            "audio": Route("gemini-tts"),
        }),
        json_mode="native", lister="gemini",
        timeouts=MappingProxyType({"audio": 30}),
        key_url="https://aistudio.google.com/apikey",
        usage_url="https://aistudio.google.com/rate-limit?timeRange=last-28-days",
    ),
    Family(
        # Workers AI has no account-less endpoint, so the account id is a setting as well as the
        # token. LiteLLM covers text only; pictures and voices go through `cloudflare.py`, because
        # FLUX.2 Klein needs multipart/form-data even for a text-only prompt. `max_tokens` is set
        # because Workers AI defaults it to about 256, which silently truncates a composed article
        # mid-JSON — the reply then parses or not depending on how long the model felt like being.
        id="cloudflare", label="Cloudflare", group="Free to start",
        hint="Text, pictures and voices, a daily allowance",
        key_label="API token",
        routes=MappingProxyType({
            "text": Route("litellm", "cloudflare/"),
            "image": Route("cloudflare"),
            "audio": Route("cloudflare"),
        }),
        fields=(Field("accountId", "Account ID", hint="On the Workers AI page"),),
        base_url="https://api.cloudflare.com/client/v4/accounts/{accountId}/ai/v1",
        params=_frozen({"text": {"max_tokens": 4096}}),
        # Aura takes `text` where MeloTTS took `prompt`, and refuses `prompt`.
        audio=_frozen({"inputField": "text"}),
        image=_frozen({"size": "native", "seed": "native"}),
        lister="cloudflare",
        key_url="https://dash.cloudflare.com/profile/api-tokens",
        usage_url="https://dash.cloudflare.com/{accountId}/ai/workers-ai",
        voices_url="https://developers.cloudflare.com/workers-ai/models/?tasks=Text-to-Speech",
    ),
    Family(
        id="groq", label="Groq", group="Free to start", hint="Fast text",
        routes=_text("groq/"), json_mode="native",
        list_url="https://api.groq.com/openai/v1",
        key_url="https://console.groq.com/keys",
        usage_url="https://console.groq.com/dashboard/usage",
        timeouts=MappingProxyType({"text": 60}),
    ),
    Family(
        # One key in front of many models. Whether JSON mode is honoured depends on the model
        # behind it, so this family claims the weaker guarantee. Its model list answers anyone, so
        # a key is checked against its own route.
        id="openrouter", label="OpenRouter", group="Free to start",
        hint="Text from many models, some free",
        routes=_text("openrouter/"),
        list_url="https://openrouter.ai/api/v1",
        check_url="https://openrouter.ai/api/v1/key",
        key_url="https://openrouter.ai/settings/keys",
        usage_url="https://openrouter.ai/activity",
        timeouts=MappingProxyType({"text": 60}),
    ),
    # ── popular ──
    Family(
        id="openai", label="OpenAI", group="Popular", hint="Text",
        routes=_text("openai/"), json_mode="native",
        list_url="https://api.openai.com/v1",
        key_url="https://platform.openai.com/api-keys",
        usage_url="https://platform.openai.com/usage",
        timeouts=MappingProxyType({"text": 60}),
    ),
    Family(
        # Anthropic ignores `response_format`, so JSON is asked for in the prompt.
        id="anthropic", label="Anthropic", group="Popular", hint="Text",
        routes=_text("anthropic/"), lister="anthropic",
        key_url="https://console.anthropic.com/settings/keys",
        usage_url="https://console.anthropic.com/settings/usage",
        timeouts=MappingProxyType({"text": 60}),
    ),
    Family(
        # A key reaches Cloud Text-to-Speech and Cloud Vision, which both take one; a credentials
        # file adds Vertex text and pictures, which take nothing else
        # (`docs/operations/vertex-setup.md`). Location stays `global` by default: the Gemini image
        # models 404 in a named region.
        #
        # Vertex image facts, each measured against the installed LiteLLM: `response_format` is
        # refused outright; `size` reaches it only as an aspect ratio, so the resolution travels in
        # `imageConfig`, the one channel that survives into `generationConfig`; `seed` is never read;
        # and Gemini 3.1 Flash Lite Image takes up to 14 reference pictures
        # (`experiments/story-picture-reference/`).
        #
        # Cloud TTS facts: `LINEAR16` is the uncompressed master, because Google's MP3 is 32 kbps
        # for a Gemini voice and a listener picked that out every time
        # (`experiments/pronunciation-encoding/`); Chinese is spelled `cmn-` on the wire; and a
        # Gemini voice is named once (`Kore`) and selected with `voice.modelName`.
        id="google-cloud", label="Google Cloud", group="Popular",
        hint="Voices and reading photos; text and pictures too",
        credential="key-or-file",
        routes=MappingProxyType({
            "text": Route("litellm", "vertex_ai/", file_only=True, vertex=True),
            "image": Route("litellm", "vertex_ai/", file_only=True, vertex=True),
            "audio": Route("google-tts"),
            "ocr": Route("google-vision"),
        }),
        fields=(
            Field("project", "Project", needed="file", hint="The Google Cloud project that is billed"),
            Field("location", "Location", needed="file", default="global",
                  choices=("global", "europe-west1", "us-central1")),
        ),
        json_mode="native",
        params=_frozen({"image": {"imageConfig": {"imageSize": "1K"}}}),
        timeouts=MappingProxyType({"text": 90, "image": 180, "audio": 30, "ocr": 15}),
        image=_frozen({"responseFormat": None, "size": "fixed", "seed": "ignored", "references": 14}),
        audio=_frozen({"encoding": "LINEAR16",
                       "wire": {"zh-Hans-CN": "cmn-CN", "zh-Hant-TW": "cmn-TW"}}),
        lister="google-cloud",
        key_url="https://console.cloud.google.com/apis/credentials",
        usage_url="https://console.cloud.google.com/billing?project={project}",
    ),
    Family(
        # Voices only. Eleven v3 and v4 take a direction as a free-text tag in square brackets at the
        # head of the words — ElevenLabs' own guide shows `[Warm, conversational tone]` — so a
        # direction is a tag here, and an older model (multilingual v2, flash) is a plain voice.
        #
        # Facts measured on the free plan, 6 Nov 2026: `wav_24000` is the best master it allows
        # (44.1 kHz PCM and WAV need Pro, 192 kbps MP3 needs Creator, each refused with a 403), and
        # every model takes `language_code`. A month's credits spent is a 402
        # `insufficient_credits`, which is an allowance spent rather than a refusal
        # (`elevenlabs.py`). The free plan is for non-commercial use, with attribution.
        id="elevenlabs", label="ElevenLabs", group="Popular",
        hint="Voices that take a direction",
        routes=MappingProxyType({"audio": Route("elevenlabs")}),
        audio=_frozen({"format": "wav_24000"}),
        timeouts=MappingProxyType({"audio": 30}),
        lister="elevenlabs",
        key_url="https://elevenlabs.io/app/settings/api-keys",
        usage_url="https://elevenlabs.io/app/usage",
    ),
    Family(
        id="mistral", label="Mistral", group="Popular", hint="Text",
        routes=_text("mistral/"), json_mode="native",
        list_url="https://api.mistral.ai/v1",
        key_url="https://console.mistral.ai/api-keys",
        usage_url="https://admin.mistral.ai/organization/usage",
        timeouts=MappingProxyType({"text": 60}),
    ),
    Family(
        id="deepseek", label="DeepSeek", group="Popular", hint="Text",
        routes=_text("deepseek/"), json_mode="native",
        list_url="https://api.deepseek.com",
        key_url="https://platform.deepseek.com/api_keys",
        usage_url="https://platform.deepseek.com/usage",
        timeouts=MappingProxyType({"text": 60}),
    ),
    # ── on your own machines ──
    Family(
        # No credential, but an address: the provider answers only where a server is listening.
        id="ollama", label="Ollama", group="On your own machines",
        hint="Text from a model on your computer",
        credential="none",
        routes=_text("ollama_chat/"), json_mode="native", lister="ollama",
        fields=(Field("baseUrl", "Address", default="http://localhost:11434",
                      hint="Where Ollama answers"),),
        base_url="{baseUrl}",
        timeouts=MappingProxyType({"text": 60}),
    ),
    Family(
        id="lm-studio", label="LM Studio", group="On your own machines",
        hint="Text from a model on your computer",
        credential="none",
        routes=_text("openai/"),
        fields=(Field("baseUrl", "Address", default="http://localhost:1234/v1",
                      hint="Where LM Studio answers"),),
        base_url="{baseUrl}", list_url="{baseUrl}",
        timeouts=MappingProxyType({"text": 60}),
    ),
    Family(
        # Anything that answers OpenAI's speech route: Kokoro-FastAPI (port 8880) and Speaches,
        # which serves Piper. Kokoro on a Mac's CPU reads a word in about a second (measured,
        # 6 Nov 2026). Voices are the server's own list; their names say their language.
        id="speech-server", label="Speech server", group="On your own machines",
        hint="Kokoro or Piper voices on your computer",
        credential="optional",
        routes=MappingProxyType({"audio": Route("openai-speech")}),
        fields=(Field("baseUrl", "Address", default="http://localhost:8880/v1",
                      hint="Where the speech server answers"),),
        base_url="{baseUrl}", list_url="{baseUrl}",
        audio=_frozen({"format": "wav"}),
        timeouts=MappingProxyType({"audio": 60}),
        lister="speech-server",
    ),
    # ── any compatible service ──
    Family(
        # Anything that speaks OpenAI's chat route. Whether it understands JSON mode is the one
        # fact the owner has to say, because nothing about the address tells.
        id="openai-compatible", label="Any compatible service", group="Any compatible service",
        hint="Give its address and key",
        credential="optional",
        routes=_text("openai/"),
        fields=(
            _BASE_URL,
            Field("jsonMode", "Understands JSON mode", needed="never", default="prompt",
                  choices=("native", "prompt")),
        ),
        base_url="{baseUrl}", list_url="{baseUrl}",
        timeouts=MappingProxyType({"text": 60}),
    ),
)

_BY_ID = {family.id: family for family in FAMILIES}


def find(identifier: str) -> Family:
    """The family by id. KeyError for one this release does not know."""
    return _BY_ID[identifier]


def _check() -> None:
    for family in FAMILIES:
        assert family.group in GROUPS, family.id
        assert family.credential in CREDENTIALS, family.id
        assert family.json_mode in JSON_MODES, family.id
        assert set(family.routes) <= set(KINDS), family.id


_check()

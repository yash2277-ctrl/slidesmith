"""THE place where the AI API is called.

Any OpenAI-compatible endpoint works (configured in .env or the in-app Settings):
    AI_BASE_URL   e.g. http://40.81.235.1:20128/v1
    AI_API_KEY    your key
    AI_MODEL      model id (leave empty to auto-pick the first one from GET {AI_BASE_URL}/models)

Requests go to POST {AI_BASE_URL}/chat/completions with stream=true.
"""
from __future__ import annotations

from typing import AsyncIterator

import openai
from openai import AsyncOpenAI

from . import config, demo

_model_cache: dict[str, str] = {}
_models_list: dict[str, list[str]] = {}
_broken: set[str] = set()  # models that failed on this endpoint (e.g. a broken vision backend)


def mark_broken(model: str | None):
    if model:
        _broken.add(model)


class ImageNotSupported(Exception):
    """The endpoint/model rejected an image in the request."""


def _client() -> AsyncOpenAI:
    return AsyncOpenAI(base_url=config.base_url(), api_key=config.api_key() or "no-key", timeout=240.0, max_retries=2)


async def list_models() -> list[str]:
    if config.demo_mode() and not config.base_url():
        return [config.DEMO_MODEL]
    page = await _client().models.list()
    _models_list[config.base_url()] = [m.id for m in page.data]
    return _models_list[config.base_url()]


async def resolve_review_model() -> str:
    """Prefer a vision-capable model for looking at rendered slides."""
    if config.review_model() and config.review_model() not in _broken:
        return config.review_model()
    try:
        models = _models_list.get(config.base_url()) or await list_models()
    except Exception:
        models = []
    vision = next((m for m in models if "vision" in m.lower() and m not in _broken), None)
    return vision or await resolve_model()


async def resolve_model() -> str:
    if config.model():
        return config.model()
    key = config.base_url()
    if key not in _model_cache:
        models = await list_models()
        if not models:
            raise RuntimeError("The endpoint returned no models. Set AI_MODEL in Settings.")
        _model_cache[key] = models[0]
    return _model_cache[key]


async def stream_chat(messages: list[dict], model: str | None = None, stop: list[str] | None = None) -> AsyncIterator[tuple[str, str]]:
    """Yield ("content", text) and ("reasoning", text) chunks as they arrive."""
    if config.demo_mode():
        async for item in demo.stream(messages):
            yield item
        return

    client = _client()
    model = model or await resolve_model()
    has_image = any(isinstance(m.get("content"), list) for m in messages)
    params = {"model": model, "messages": messages, "stream": True,
              "max_tokens": config.max_tokens(), "temperature": config.temperature()}
    if stop:
        params["stop"] = stop
    try:
        stream = await client.chat.completions.create(**params)
    except openai.BadRequestError:
        # some servers/models reject max_tokens or temperature - retry with the bare minimum
        params.pop("max_tokens")
        params.pop("temperature")
        params.pop("stop", None)
        try:
            stream = await client.chat.completions.create(**params)
        except openai.BadRequestError:
            if has_image:
                raise ImageNotSupported()
            raise

    async for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        extra = getattr(delta, "model_extra", None) or {}
        reasoning = extra.get("reasoning_content") or extra.get("reasoning")
        if isinstance(reasoning, str) and reasoning:
            yield "reasoning", reasoning
        if delta.content:
            yield "content", delta.content


KNOWN_ERRORS = [  # (substring of a raw error, plain explanation)
    ("browser session failed", "The AI server's vision model is broken on the server side (its browser backend is missing). Reviews now continue without the slide image."),
    ("ms-playwright", "The AI server's vision model is broken on the server side (its browser backend is missing). Reviews now continue without the slide image."),
    ("ReadError", "The connection to the AI server dropped in the middle of a reply."),
    ("RemoteProtocolError", "The connection to the AI server dropped in the middle of a reply."),
    ("[502]", "The AI server had a temporary problem (502)."),
    ("[503]", "The AI server is temporarily unavailable (503)."),
    ("[504]", "The AI server timed out (504)."),
]


def explain(text: str) -> str:
    """Turn a raw error string into a short, plain explanation (unchanged if unknown)."""
    for needle, plain in KNOWN_ERRORS:
        if needle in (text or ""):
            return plain
    return text


def friendly_error(exc: Exception) -> str:
    base = config.base_url() or "(not set)"
    if isinstance(exc, openai.APIConnectionError) or type(exc).__module__.startswith(("httpx", "httpcore")):
        if type(exc).__name__ in ("ReadError", "RemoteProtocolError", "ReadTimeout"):
            return explain("ReadError") + " Try again."
        return f"Can't reach the AI endpoint at {base}. Check that the server is running and reachable, then try again."
    if isinstance(exc, openai.AuthenticationError):
        return "The AI endpoint rejected the API key (401). Update it in Settings."
    if isinstance(exc, openai.NotFoundError):
        return f"The endpoint returned 404 - check the base URL ({base}) and model name."
    if isinstance(exc, openai.RateLimitError):
        return "Rate limited by the AI endpoint. Wait a moment and try again."
    if isinstance(exc, openai.APIStatusError):
        return explain(f"[{exc.status_code}]") if f"[{exc.status_code}]" in str(KNOWN_ERRORS) else f"AI endpoint error {exc.status_code}: {str(exc.message)[:200]}"
    return explain(f"{type(exc).__name__}: {exc}")[:300]

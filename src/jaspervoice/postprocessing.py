"""Post-processing pipeline step — runs after Whisper transcription, before text injection.

This module defines the interface that future OpenCode / cloud providers will
implement. Currently includes NoopPostProcessor and OpenCodePostProcessor.
"""

from __future__ import annotations

import json as _json
import logging
import os
import re
import time
import urllib.request as _urllib
from dataclasses import dataclass
from typing import Any, Callable, Optional
from urllib.error import HTTPError as _HTTPError, URLError as _URLError

log = logging.getLogger(__name__)

OUTPUT_MODES = {"raw", "clean", "prompt", "commit", "docs", "command"}
DEFAULT_OUTPUT_MODE = "raw"

FAST_MODES = {"clean", "prompt", "commit", "command"}
SMART_MODES = {"docs"}

_ENV_VAR_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SECRET_VALUE_RE = re.compile(r"^(sk-|sk-proj-|gh[pousr]_|xox[baprs]-|AIza)")

PROMPTS: dict[str, str] = {
    "clean": (
        "You clean up dictated text. Fix punctuation, capitalization, spacing, "
        "and obvious transcription mistakes. Preserve the user's meaning. "
        "Return only the corrected text."
    ),
    "prompt": (
        "Transform this dictated text into a clear coding-agent prompt. "
        "Keep it concise, actionable, and specific. Preserve all technical terms. "
        "Return only the final prompt."
    ),
    "commit": (
        "Transform this dictated change description into a concise commit message. "
        "Prefer Conventional Commits. Return only the commit message."
    ),
    "docs": (
        "Rewrite this dictated text as clear technical documentation. "
        "Preserve meaning and technical accuracy. Return only the documentation text."
    ),
    "command": (
        "Transform this dictated instruction into a short, direct command "
        "for a coding agent. Return only the command."
    ),
}


RequestFn = Callable[[str, bytes, dict[str, str], int], bytes]


def is_valid_env_var_name(value: object) -> bool:
    """True when value is a plain environment-variable name, not a secret."""
    if not isinstance(value, str):
        return False
    stripped = value.strip()
    return bool(_ENV_VAR_NAME_RE.fullmatch(stripped)) and not _SECRET_VALUE_RE.match(stripped)


def _provider_http_error(action: str, code: int, reason: str, api_key_env: str, has_key: bool) -> str:
    status = f"HTTP {code}" + (f" {reason}" if reason else "")
    if code not in (401, 403):
        return f"{action} failed: {status}"
    if not is_valid_env_var_name(api_key_env):
        auth_hint = (
            "The API key field must contain an environment-variable name, not the key itself. "
            "Use a name like OPENCODE_API_KEY, set that variable outside JasperVoice, "
            "then restart the app."
        )
    elif has_key:
        auth_hint = (
            f"The key loaded from {api_key_env.strip()} was rejected by the provider. "
            "Check that the key is valid and allowed to list models."
        )
    else:
        auth_hint = (
            f"No value is set for {api_key_env.strip()} in this JasperVoice process. "
            "Set the environment variable outside JasperVoice, then restart the app."
        )
    return f"{action} was rejected ({status}). {auth_hint}"


def _model_fetch_http_error(code: int, reason: str, api_key_env: str, has_key: bool) -> str:
    return _provider_http_error("Model list request", code, reason, api_key_env, has_key)


def _api_call_http_error(code: int, reason: str, api_key_env: str, has_key: bool) -> str:
    return _provider_http_error("AI Polish request", code, reason, api_key_env, has_key)


@dataclass
class PostProcessResult:
    text: str
    provider: str
    mode: str
    model: Optional[str]
    latency_ms: int


class PostProcessorError(RuntimeError):
    """Raised when post-processing fails (provider unavailable, timeout, etc.)."""


class PostProcessor:
    """Abstract post-processor. process() receives raw dictation text and
    returns a PostProcessResult. The default implementation is a no-op.
    """

    def process(self, text: str, mode: str = "raw") -> PostProcessResult:
        raise NotImplementedError


class NoopPostProcessor(PostProcessor):
    """Passes text through unchanged. Used when post_processing_enabled=False
    or when no real provider is configured."""

    def __init__(self) -> None:
        pass

    def process(self, text: str, mode: str = "raw") -> PostProcessResult:
        t0 = time.monotonic()
        effective_mode = mode if mode in OUTPUT_MODES else DEFAULT_OUTPUT_MODE
        if mode not in OUTPUT_MODES:
            log.warning("Unknown output_mode %r, falling back to %r", mode, effective_mode)
        result = PostProcessResult(
            text=text,
            provider="none",
            mode=effective_mode,
            model=None,
            latency_ms=round((time.monotonic() - t0) * 1000),
        )
        return result


def _build_url(base_url: str) -> str:
    """Build the chat completions endpoint URL from a base_url.

    If base_url ends with '/v1', use {base_url}/chat/completions.
    Otherwise, use {base_url}/v1/chat/completions.
    Trailing slashes are collapsed.
    """
    base = base_url.rstrip("/")
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def _build_models_url(base_url: str) -> str:
    """Build the model-list endpoint URL (same '/v1' convention as _build_url)."""
    base = base_url.rstrip("/")
    if base.endswith("/v1"):
        return f"{base}/models"
    return f"{base}/v1/models"


def fetch_available_models(
    base_url: str,
    api_key_env: str = "OPENCODE_API_KEY",
    timeout_s: int = 20,
    request_fn: Optional[Callable[[str, dict[str, str], int], bytes]] = None,
) -> list[str]:
    """GET the provider's model list (OpenAI-compatible `/models` endpoint).

    Returns sorted model ids. The API key is optional — local servers such as
    Ollama or LM Studio accept unauthenticated requests. Raises
    PostProcessorError on any failure; never raises raw exceptions.
    """
    if not base_url.strip():
        raise PostProcessorError("Endpoint is empty. Fill in the provider base URL first.")

    headers = {"Accept": "application/json", "User-Agent": "JasperVoice"}
    api_key = os.environ.get(api_key_env.strip()) if is_valid_env_var_name(api_key_env) else None
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    def _default_get(url: str, hdrs: dict[str, str], timeout: int) -> bytes:
        req = _urllib.Request(url, headers=hdrs, method="GET")
        try:
            with _urllib.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except _HTTPError as e:
            raise PostProcessorError(
                _model_fetch_http_error(e.code, str(e.reason or ""), api_key_env, bool(api_key))
            ) from e
        except _URLError as e:
            raise PostProcessorError(f"HTTP request failed: {e}") from e

    url = _build_models_url(base_url)
    try:
        raw = (request_fn or _default_get)(url, headers, timeout_s)
    except PostProcessorError:
        raise
    except _HTTPError as e:
        raise PostProcessorError(
            _model_fetch_http_error(e.code, str(e.reason or ""), api_key_env, bool(api_key))
        ) from e
    except Exception as e:
        raise PostProcessorError(f"Could not reach {url}: {e}") from e

    try:
        data = _json.loads(raw.decode("utf-8"))
    except Exception as e:
        raise PostProcessorError(f"Invalid JSON response from API: {e}") from e

    # OpenAI shape: {"data": [{"id": ...}, ...]}; some servers return a bare list.
    items = data.get("data") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise PostProcessorError("API response has no model list")
    models = []
    for item in items:
        if isinstance(item, dict) and item.get("id"):
            models.append(str(item["id"]))
        elif isinstance(item, str) and item:
            models.append(item)
    if not models:
        raise PostProcessorError("The provider returned an empty model list")
    return sorted(set(models))


def _make_request(url: str, body: bytes, headers: dict[str, str], timeout_s: int) -> bytes:
    """Default request function. Uses stdlib urllib."""
    req = _urllib.Request(url, data=body, headers=headers, method="POST")
    try:
        with _urllib.urlopen(req, timeout=timeout_s) as resp:
            return resp.read()
    except _HTTPError:
        raise
    except _URLError as e:
        raise PostProcessorError(f"HTTP request failed: {e}") from e


class OpenCodePostProcessor(PostProcessor):
    """Calls an OpenAI-compatible chat completions API to refine dictated text.

    Only text is sent to the API — never audio.
    """

    def __init__(
        self,
        base_url: str,
        api_key_env: str = "OPENCODE_API_KEY",
        fast_model: str = "DeepSeek V4 Flash",
        smart_model: str = "Qwen3.7 Max",
        timeout_s: int = 20,
        request_fn: Optional[RequestFn] = None,
    ) -> None:
        self._base_url = base_url
        self._api_key_env = api_key_env
        self._fast_model = fast_model
        self._smart_model = smart_model
        self._timeout_s = timeout_s
        self._request_fn: RequestFn = request_fn or _make_request

    def process(self, text: str, mode: str = "raw") -> PostProcessResult:
        t0 = time.monotonic()

        effective_mode = mode if mode in OUTPUT_MODES else DEFAULT_OUTPUT_MODE
        if mode not in OUTPUT_MODES:
            log.warning("Unknown output_mode %r, falling back to %r", mode, effective_mode)

        if effective_mode == "raw":
            return PostProcessResult(
                text=text,
                provider="opencode",
                mode="raw",
                model=None,
                latency_ms=round((time.monotonic() - t0) * 1000),
            )

        if not self._base_url:
            raise PostProcessorError(
                "OpenCode base URL is not configured. Set opencode_base_url in settings."
            )

        model = self._fast_model if effective_mode in FAST_MODES else self._smart_model
        system_prompt = PROMPTS.get(effective_mode, PROMPTS["clean"])

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            "temperature": 0.2,
        }
        body = _json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
        }
        api_key = os.environ.get(self._api_key_env.strip()) if is_valid_env_var_name(self._api_key_env) else None
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        url = _build_url(self._base_url)
        try:
            resp_bytes = self._request_fn(url, body, headers, self._timeout_s)
        except _HTTPError as e:
            raise PostProcessorError(
                _api_call_http_error(e.code, str(e.reason or ""), self._api_key_env, bool(api_key))
            ) from e
        except PostProcessorError:
            raise
        except Exception as e:
            raise PostProcessorError(f"API call failed: {e}") from e

        try:
            resp_data = _json.loads(resp_bytes.decode("utf-8"))
        except Exception as e:
            raise PostProcessorError(f"Invalid JSON response from API: {e}") from e

        choices = resp_data.get("choices")
        if not choices or not isinstance(choices, list):
            raise PostProcessorError("API response missing 'choices' array")
        content = choices[0].get("message", {}).get("content", "")
        if not content or not isinstance(content, str):
            raise PostProcessorError("API returned empty content")

        latency_ms = round((time.monotonic() - t0) * 1000)
        log.info(
            "OpenCode provider=%s mode=%s model=%s latency=%dms",
            "opencode",
            effective_mode,
            model,
            latency_ms,
        )
        return PostProcessResult(
            text=content.strip(),
            provider="opencode",
            mode=effective_mode,
            model=model,
            latency_ms=latency_ms,
        )

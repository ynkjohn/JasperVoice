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

# Common env var names users tend to have set. The diagnostic checks these to
# tell the user "you already have OPENAI_API_KEY, just point the field at it"
# instead of failing with an opaque 403.
COMMON_API_KEY_ENVS: tuple[str, ...] = (
    "OPENCODE_API_KEY",
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "ANTHROPIC_API_KEY",
    "GROQ_API_KEY",
    "MISTRAL_API_KEY",
    "GEMINI_API_KEY",
)

_PRESERVE_LANGUAGE = (
    "Keep the original language or mixture of languages used in the dictation. "
    "Only translate if explicitly requested. "
)

PROMPTS: dict[str, str] = {
    "clean": (
        "You clean up dictated text. Fix punctuation, capitalization, spacing, "
        "and obvious transcription mistakes. Preserve the user's meaning. "
        "Return only the corrected text. "
        "Keep the original language or mixture of languages in the dictated text. "
        "Do not translate unless the user explicitly requests translation."
    ),
    "prompt": (
        "Polish the dictation for a coding assistant. Copyedit it in its original language. "
        "Preserve the request, facts, names, and technical terms. Return only the polished dictation."
    ),
    "commit": (
        "Summarize the dictated changes using words from the original language. "
        "Return only one Conventional Commit subject. Use fix: for bug fixes and feat: for new features. "
        "Preserve the language of every phrase. "
        "The output language comes from the input text. Copy the original meaningful words where possible."
    ),
    "docs": _PRESERVE_LANGUAGE + (
        "Edit the dictated technical instructions for clarity. Fix punctuation and phrasing. "
        "Keep the original language and menu labels. Return only the edited dictation."
    ),
    "command": _PRESERVE_LANGUAGE + (
        "Edit the dictated instruction for clarity and brevity. Preserve the wording of any literal "
        "shell command, options, and paths. Return only the edited instruction in the original language."
    ),
}


def default_system_prompt(mode: str, language: str = "") -> str:
    prompt = PROMPTS.get(mode)
    if prompt is None:
        return ""
    if re.fullmatch(r"[a-z]{2,3}", language or ""):
        return f"{prompt} Whisper language code: {language}."
    return prompt


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
    if not api_key_env.strip():
        auth_hint = (
            "No API key was sent. This endpoint requires authorization or denied this request. "
            "Set the provider's environment-variable name in AI Polish and restart JasperVoice "
            "after adding the key to Windows."
        )
    elif not is_valid_env_var_name(api_key_env):
        auth_hint = (
            "The API key field must contain an environment-variable name, not the key itself. "
            "Use a name like OPENCODE_API_KEY, set that variable outside JasperVoice, "
            "then restart the app."
        )
    elif has_key:
        auth_hint = (
            f"The key loaded from {api_key_env.strip()} was rejected by the provider. "
            "Check the key and its permissions for this endpoint and model."
        )
    else:
        alt = _detect_alt_api_key_env(api_key_env)
        alt_hint = (
            f" Detected a value under '{alt}'; change the API key env var field "
            f"to '{alt}' to use it."
            if alt else ""
        )
        auth_hint = (
            f"No value is set for {api_key_env.strip()} in this JasperVoice process. "
            "Open AI Polish and use Check key for setup details. "
            "For remote APIs: set the env var in Windows (Win+R -> sysdm.cpl -> "
            "Advanced -> Environment Variables), then close and reopen JasperVoice. "
            "For local servers (Ollama, LM Studio): leave the field empty."
            f"{alt_hint}"
        )
    return f"{action} was rejected ({status}). {auth_hint}"


def _detect_alt_api_key_env(configured: str) -> Optional[str]:
    """Return the first COMMON_API_KEY_ENVS name that has a value set,
    excluding the one the user already configured. Used to nudge users who
    already have e.g. OPENAI_API_KEY set but typed OPENCODE_API_KEY in the field."""
    configured = (configured or "").strip()
    for alt in COMMON_API_KEY_ENVS:
        if alt == configured:
            continue
        if os.environ.get(alt):
            return alt
    return None


def _model_fetch_http_error(code: int, reason: str, api_key_env: str, has_key: bool) -> str:
    return _provider_http_error("Model list request", code, reason, api_key_env, has_key)


def _api_call_http_error(error: _HTTPError, api_key_env: str, has_key: bool) -> str:
    message = _provider_http_error("AI Polish request", error.code, str(error.reason or ""), api_key_env, has_key)
    if error.code != 400:
        return message

    try:
        body = _json.loads(error.read(8192))
    except (OSError, ValueError):
        return message

    details = body.get("error") if isinstance(body, dict) else None
    if isinstance(details, dict) and (
        details.get("type") == "exceed_context_size_error"
        or details.get("code") == "context_length_exceeded"
    ):
        return f"{message}. The dictation and style prompt exceed the model's context window."
    return message


def diagnose_polish_config(base_url: str, api_key_env: str = "OPENCODE_API_KEY") -> dict:
    """Inspect the local Polish config without making any network call.

    The result is a plain dict the UI can render verbatim. It tells the user
    exactly what's missing (or already wired) so they don't have to guess from
    an opaque 403. Safe to call from the GUI thread.
    """
    base_url = (base_url or "").strip()
    api_key_env = (api_key_env or "").strip() or "OPENCODE_API_KEY"

    result: dict = {
        "base_url": base_url,
        "api_key_env": api_key_env,
        "base_url_set": bool(base_url),
        "env_var_name_valid": False,
        "env_var_set": False,
        "env_var_value_len": 0,
        "detected_alt_env_var": None,
        "issues": [],
    }

    if not base_url:
        result["issues"].append("Endpoint URL is empty.")

    if not is_valid_env_var_name(api_key_env):
        result["issues"].append(
            f"API key env var '{api_key_env}' is not a valid environment-variable name. "
            "Use a name like OPENCODE_API_KEY, not the key itself."
        )
        return result

    result["env_var_name_valid"] = True
    value = os.environ.get(api_key_env)
    if value:
        result["env_var_set"] = True
        result["env_var_value_len"] = len(value)
        return result

    for alt in COMMON_API_KEY_ENVS:
        if alt == api_key_env:
            continue
        if os.environ.get(alt):
            result["detected_alt_env_var"] = alt
            result["issues"].append(
                f"'{api_key_env}' is not set, but '{alt}' is set. "
                f"Change the API key env var field to '{alt}' to use it, "
                f"or set '{api_key_env}' in Windows and restart JasperVoice."
            )
            return result

    result["issues"].append(
        f"'{api_key_env}' is not set in this JasperVoice process. "
        "For remote APIs: set it in Windows "
        "(Win+R -> sysdm.cpl -> Advanced -> Environment Variables), "
        "then close and reopen JasperVoice. "
        "For local servers (Ollama, LM Studio): leave the field empty."
    )
    return result


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

    def process(self, text: str, mode: str = "raw", *, language: str = "") -> PostProcessResult:
        raise NotImplementedError


class NoopPostProcessor(PostProcessor):
    """Passes text through unchanged. Used when post_processing_enabled=False
    or when no real provider is configured."""

    def __init__(self) -> None:
        pass

    def process(self, text: str, mode: str = "raw", *, language: str = "") -> PostProcessResult:
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
        custom_prompts: Optional[dict[str, str]] = None,
    ) -> None:
        self._base_url = base_url
        self._api_key_env = api_key_env
        self._fast_model = fast_model
        self._smart_model = smart_model
        self._timeout_s = timeout_s
        self._request_fn: RequestFn = request_fn or _make_request
        self._custom_prompts = dict(custom_prompts or {})

    def process(self, text: str, mode: str = "raw", *, language: str = "") -> PostProcessResult:
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
        system_prompt = self._custom_prompts.get(effective_mode) or default_system_prompt(effective_mode, language)

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
                _api_call_http_error(e, self._api_key_env, bool(api_key))
            ) from e
        except PostProcessorError:
            raise
        except Exception as e:
            raise PostProcessorError(f"API call failed: {e}") from e

        try:
            resp_data = _json.loads(resp_bytes.decode("utf-8"))
        except Exception as e:
            raise PostProcessorError(f"Invalid JSON response from API: {e}") from e

        choices = resp_data.get("choices") if isinstance(resp_data, dict) else None
        if not isinstance(choices, list) or not choices:
            raise PostProcessorError("API response missing 'choices' array")
        choice = choices[0]
        if not isinstance(choice, dict):
            raise PostProcessorError("API response has an invalid completion choice")

        finish_reason = choice.get("finish_reason")
        if finish_reason == "length":
            raise PostProcessorError("The model stopped at its token limit before AI Polish completed")
        if finish_reason == "content_filter":
            raise PostProcessorError("The provider's content filter stopped AI Polish")
        if finish_reason in ("tool_calls", "function_call"):
            raise PostProcessorError("The model returned a tool call instead of polished text")

        message = choice.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
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

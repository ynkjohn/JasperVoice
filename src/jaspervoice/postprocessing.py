"""Post-processing pipeline step — runs after Whisper transcription, before text injection.

This module defines the interface that future OpenCode / cloud providers will
implement. Currently includes NoopPostProcessor and OpenCodePostProcessor.
"""

from __future__ import annotations

import json as _json
import logging
import os
import time
import urllib.request as _urllib
from dataclasses import dataclass
from typing import Any, Callable, Optional
from urllib.error import URLError as _URLError

log = logging.getLogger(__name__)

OUTPUT_MODES = {"raw", "clean", "prompt", "commit", "docs", "command"}
DEFAULT_OUTPUT_MODE = "raw"

FAST_MODES = {"clean", "prompt", "commit", "command"}
SMART_MODES = {"docs"}

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


def _make_request(url: str, body: bytes, headers: dict[str, str], timeout_s: int) -> bytes:
    """Default request function. Uses stdlib urllib."""
    req = _urllib.Request(url, data=body, headers=headers, method="POST")
    try:
        with _urllib.urlopen(req, timeout=timeout_s) as resp:
            return resp.read()
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

        api_key = os.environ.get(self._api_key_env)
        if not api_key:
            raise PostProcessorError(
                f"API key not found. Set the {self._api_key_env} environment variable."
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
            "Authorization": f"Bearer {api_key}",
        }

        url = _build_url(self._base_url)
        try:
            resp_bytes = self._request_fn(url, body, headers, self._timeout_s)
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

import json
import logging
import os
import urllib.error

import pytest

from jaspervoice.postprocessing import (
    NoopPostProcessor,
    OpenCodePostProcessor,
    PostProcessorError,
    PostProcessResult,
    OUTPUT_MODES,
    DEFAULT_OUTPUT_MODE,
    PROMPTS,
    _build_url,
    is_valid_env_var_name,
)


def test_noop_returns_same_text():
    pp = NoopPostProcessor()
    result = pp.process("hello world", mode="raw")
    assert result.text == "hello world"


def test_noop_accepts_all_valid_modes():
    pp = NoopPostProcessor()
    for mode in OUTPUT_MODES:
        result = pp.process("test", mode=mode)
        assert result.text == "test"
        assert result.mode == mode


def test_noop_result_has_provider_none():
    pp = NoopPostProcessor()
    result = pp.process("hello")
    assert result.provider == "none"


def test_noop_result_model_is_none():
    pp = NoopPostProcessor()
    result = pp.process("hello")
    assert result.model is None


def test_noop_invalid_mode_falls_back_to_raw():
    pp = NoopPostProcessor()
    result = pp.process("hello", mode="invalid_mode")
    assert result.text == "hello"
    assert result.mode == DEFAULT_OUTPUT_MODE


def test_noop_latency_is_nonnegative():
    pp = NoopPostProcessor()
    result = pp.process("hello")
    assert result.latency_ms >= 0


def test_noop_default_mode_is_raw():
    pp = NoopPostProcessor()
    result = pp.process("hello")
    assert result.mode == "raw"


# --- OpenCodePostProcessor tests ---

def _fake_request_fn(payload_check=None, response_json=None, side_effect=None):
    """Factory for injectable request_fn."""

    def _fn(url, body, headers, timeout_s):
        if side_effect is not None:
            raise side_effect
        if payload_check:
            payload_check(json.loads(body.decode("utf-8")), headers)
        if response_json is not None:
            return json.dumps(response_json).encode("utf-8")
        return json.dumps({
            "choices": [{"message": {"content": "final text"}}]
        }).encode("utf-8")

    return _fn


def test_build_url_with_v1_suffix():
    assert _build_url("https://api.example.com/v1") == "https://api.example.com/v1/chat/completions"


def test_build_url_without_v1_suffix():
    assert _build_url("https://api.example.com") == "https://api.example.com/v1/chat/completions"


def test_build_url_strips_trailing_slashes():
    assert _build_url("https://api.example.com/v1/") == "https://api.example.com/v1/chat/completions"


def test_opencode_raw_mode_does_not_call_api():
    called = []

    def rf(url, body, headers, timeout_s):
        called.append(1)
        return b"{}"

    pp = OpenCodePostProcessor(
        base_url="https://api.example.com",
        request_fn=rf,
    )
    result = pp.process("hello world", mode="raw")
    assert result.text == "hello world"
    assert result.provider == "opencode"
    assert result.model is None
    assert len(called) == 0


def test_opencode_clean_mode_uses_fast_model():
    def check(payload, headers):
        assert payload["model"] == "fast-model"
        assert payload["messages"][0]["content"] == PROMPTS["clean"]
        assert payload["messages"][1]["content"] == "hello world"
        assert payload["temperature"] == 0.2
        assert headers["Authorization"] == "Bearer test-key-123"

    pp = OpenCodePostProcessor(
        base_url="https://api.example.com",
        fast_model="fast-model",
        smart_model="smart-model",
        request_fn=_fake_request_fn(payload_check=check),
    )
    with pytest.MonkeyPatch().context() as mp:
        mp.setenv("OPENCODE_API_KEY", "test-key-123")
        result = pp.process("hello world", mode="clean")
    assert result.text == "final text"
    assert result.provider == "opencode"
    assert result.mode == "clean"
    assert result.model == "fast-model"
    assert result.latency_ms >= 0


def test_opencode_docs_mode_uses_smart_model():
    def check(payload, headers):
        assert payload["model"] == "smart-model"
        assert payload["messages"][0]["content"] == PROMPTS["docs"]

    pp = OpenCodePostProcessor(
        base_url="https://api.example.com",
        fast_model="fast-model",
        smart_model="smart-model",
        request_fn=_fake_request_fn(payload_check=check),
    )
    with pytest.MonkeyPatch().context() as mp:
        mp.setenv("OPENCODE_API_KEY", "test-key-123")
        result = pp.process("hello world", mode="docs")
    assert result.text == "final text"
    assert result.model == "smart-model"


def test_opencode_prompt_mode_uses_fast_model():
    def check(payload, headers):
        assert payload["model"] == "fast-model"

    pp = OpenCodePostProcessor(
        base_url="https://api.example.com",
        fast_model="fast-model",
        smart_model="smart-model",
        request_fn=_fake_request_fn(payload_check=check),
    )
    with pytest.MonkeyPatch().context() as mp:
        mp.setenv("OPENCODE_API_KEY", "test-key-123")
        result = pp.process("hello world", mode="prompt")
    assert result.model == "fast-model"


def test_opencode_commit_mode_uses_fast_model():
    def check(payload, headers):
        assert payload["model"] == "fast-model"
        assert payload["messages"][0]["content"] == PROMPTS["commit"]

    pp = OpenCodePostProcessor(
        base_url="https://api.example.com",
        fast_model="fast-model",
        smart_model="smart-model",
        request_fn=_fake_request_fn(payload_check=check),
    )
    with pytest.MonkeyPatch().context() as mp:
        mp.setenv("OPENCODE_API_KEY", "test-key-123")
        result = pp.process("hello world", mode="commit")
    assert result.model == "fast-model"


def test_opencode_command_mode_uses_fast_model():
    def check(payload, headers):
        assert payload["model"] == "fast-model"
        assert payload["messages"][0]["content"] == PROMPTS["command"]

    pp = OpenCodePostProcessor(
        base_url="https://api.example.com",
        fast_model="fast-model",
        smart_model="smart-model",
        request_fn=_fake_request_fn(payload_check=check),
    )
    with pytest.MonkeyPatch().context() as mp:
        mp.setenv("OPENCODE_API_KEY", "test-key-123")
        result = pp.process("hello world", mode="command")
    assert result.model == "fast-model"


def test_opencode_invalid_mode_falls_back_to_raw():
    called = []

    def rf(url, body, headers, timeout_s):
        called.append(1)
        return b"{}"

    pp = OpenCodePostProcessor(
        base_url="https://api.example.com",
        request_fn=rf,
    )
    with pytest.MonkeyPatch().context() as mp:
        mp.setenv("OPENCODE_API_KEY", "test-key-123")
        result = pp.process("hello world", mode="super_mode")
    assert result.text == "hello world"
    assert result.mode == "raw"
    assert len(called) == 0


def test_opencode_empty_base_url_raises():
    pp = OpenCodePostProcessor(base_url="", request_fn=_fake_request_fn())
    with pytest.MonkeyPatch().context() as mp:
        mp.setenv("OPENCODE_API_KEY", "key")
        with pytest.raises(PostProcessorError, match="base URL"):
            pp.process("hello", mode="clean")


def test_opencode_missing_api_key_omits_auth_and_succeeds():
    def check(payload, headers):
        assert payload["model"]
        assert "Authorization" not in headers

    pp = OpenCodePostProcessor(
        base_url="https://api.example.com",
        request_fn=_fake_request_fn(payload_check=check),
    )
    with pytest.MonkeyPatch().context() as mp:
        mp.delenv("OPENCODE_API_KEY", raising=False)
        result = pp.process("hello", mode="clean")
    assert result.text == "final text"


def test_opencode_api_key_not_in_error_message():
    pp = OpenCodePostProcessor(
        base_url="https://api.example.com",
        api_key_env="MY_SECRET",
        request_fn=_fake_request_fn(side_effect=PostProcessorError("network error")),
    )
    with pytest.MonkeyPatch().context() as mp:
        mp.setenv("MY_SECRET", "sk-super-secret-12345")
        with pytest.raises(PostProcessorError) as exc_info:
            pp.process("hello", mode="clean")
    msg = str(exc_info.value)
    assert "sk-super-secret-12345" not in msg


def test_opencode_http_error_raises():
    pp = OpenCodePostProcessor(
        base_url="https://api.example.com",
        request_fn=_fake_request_fn(side_effect=PostProcessorError("HTTP 500")),
    )
    with pytest.MonkeyPatch().context() as mp:
        mp.setenv("OPENCODE_API_KEY", "key")
        with pytest.raises(PostProcessorError, match="HTTP 500"):
            pp.process("hello", mode="clean")


def test_opencode_403_without_env_var_explains_auth(monkeypatch):
    def fake_request(url, body, headers, timeout_s):
        raise urllib.error.HTTPError(url, 403, "Forbidden", None, None)

    monkeypatch.delenv("OPENCODE_API_KEY", raising=False)
    pp = OpenCodePostProcessor(base_url="https://api.example.com", request_fn=fake_request)
    with pytest.raises(PostProcessorError) as exc_info:
        pp.process("hello", mode="clean")
    msg = str(exc_info.value)
    assert "403" in msg
    assert "OPENCODE_API_KEY" in msg
    assert "restart" in msg


def test_opencode_403_raw_key_env_does_not_leak_secret():
    secret = "sk-" + "a" * 48

    def fake_request(url, body, headers, timeout_s):
        raise urllib.error.HTTPError(url, 403, "Forbidden", None, None)

    pp = OpenCodePostProcessor(
        base_url="https://api.example.com",
        api_key_env=secret,
        request_fn=fake_request,
    )
    with pytest.raises(PostProcessorError) as exc_info:
        pp.process("hello", mode="clean")
    msg = str(exc_info.value)
    assert secret not in msg
    assert "not the key itself" in msg


def test_opencode_invalid_json_response_raises():
    pp = OpenCodePostProcessor(
        base_url="https://api.example.com",
        request_fn=lambda url, body, headers, ts: b"not json",
    )
    with pytest.MonkeyPatch().context() as mp:
        mp.setenv("OPENCODE_API_KEY", "key")
        with pytest.raises(PostProcessorError, match="Invalid JSON"):
            pp.process("hello", mode="clean")


def test_opencode_missing_choices_raises():
    pp = OpenCodePostProcessor(
        base_url="https://api.example.com",
        request_fn=_fake_request_fn(response_json={"no_choices": True}),
    )
    with pytest.MonkeyPatch().context() as mp:
        mp.setenv("OPENCODE_API_KEY", "key")
        with pytest.raises(PostProcessorError, match="choices"):
            pp.process("hello", mode="clean")


def test_opencode_empty_content_raises():
    pp = OpenCodePostProcessor(
        base_url="https://api.example.com",
        request_fn=_fake_request_fn(response_json={"choices": [{"message": {"content": ""}}]}),
    )
    with pytest.MonkeyPatch().context() as mp:
        mp.setenv("OPENCODE_API_KEY", "key")
        with pytest.raises(PostProcessorError, match="empty content"):
            pp.process("hello", mode="clean")


def test_opencode_success_returns_content():
    pp = OpenCodePostProcessor(
        base_url="https://api.example.com",
        request_fn=_fake_request_fn(response_json={
            "choices": [{"message": {"content": "  corrected text  "}}]
        }),
    )
    with pytest.MonkeyPatch().context() as mp:
        mp.setenv("OPENCODE_API_KEY", "key")
        result = pp.process("hello", mode="clean")
    assert result.text == "corrected text"
    assert result.provider == "opencode"
    assert result.latency_ms >= 0


def test_opencode_default_api_key_env():
    pp = OpenCodePostProcessor(
        base_url="https://api.example.com",
        request_fn=_fake_request_fn(),
    )
    with pytest.MonkeyPatch().context() as mp:
        mp.setenv("OPENCODE_API_KEY", "my-key")
        result = pp.process("hello", mode="clean")
    assert result.text == "final text"


def test_opencode_success_with_info_logging_does_not_raise(caplog):
    pp = OpenCodePostProcessor(
        base_url="https://api.example.com",
        request_fn=_fake_request_fn(response_json={
            "choices": [{"message": {"content": "corrected text"}}]
        }),
    )
    with pytest.MonkeyPatch().context() as mp:
        mp.setenv("OPENCODE_API_KEY", "key-12345")
        caplog.set_level(logging.INFO, logger="jaspervoice.postprocessing")
        result = pp.process("hello world", mode="clean")

    assert result.text == "corrected text"
    assert result.provider == "opencode"
    logs = caplog.text
    assert "key-12345" not in logs
    assert "hello world" not in logs
    assert "opencode" in logs.lower() or "OpenCode" in logs


# --- Model list fetching (AI Polish "Fetch models") ---

def test_build_models_url_appends_v1():
    from jaspervoice.postprocessing import _build_models_url

    assert _build_models_url("https://api.example.com") == "https://api.example.com/v1/models"
    assert _build_models_url("http://localhost:11434/v1") == "http://localhost:11434/v1/models"
    assert _build_models_url("http://host/v1/") == "http://host/v1/models"


def test_fetch_available_models_parses_openai_shape():
    from jaspervoice.postprocessing import fetch_available_models

    def fake_get(url, headers, timeout):
        assert url.endswith("/v1/models")
        return json.dumps({"data": [{"id": "b-model"}, {"id": "a-model"}, {"id": "a-model"}]}).encode()

    models = fetch_available_models("http://localhost:1234", request_fn=fake_get)
    assert models == ["a-model", "b-model"]  # sorted, deduplicated


def test_fetch_available_models_accepts_bare_list():
    from jaspervoice.postprocessing import fetch_available_models

    def fake_get(url, headers, timeout):
        return json.dumps(["m2", "m1"]).encode()

    assert fetch_available_models("http://x/v1", request_fn=fake_get) == ["m1", "m2"]


def test_fetch_available_models_sends_bearer_when_key_set(monkeypatch):
    from jaspervoice.postprocessing import fetch_available_models

    monkeypatch.setenv("MY_TEST_KEY", "sekret")
    seen = {}

    def fake_get(url, headers, timeout):
        seen.update(headers)
        return json.dumps({"data": [{"id": "m"}]}).encode()

    fetch_available_models("http://x", api_key_env="MY_TEST_KEY", request_fn=fake_get)
    assert seen.get("Authorization") == "Bearer sekret"


def test_fetch_available_models_no_key_omits_auth(monkeypatch):
    from jaspervoice.postprocessing import fetch_available_models

    monkeypatch.delenv("NOPE_KEY", raising=False)
    seen = {}

    def fake_get(url, headers, timeout):
        seen.update(headers)
        return json.dumps({"data": [{"id": "m"}]}).encode()

    fetch_available_models("http://x", api_key_env="NOPE_KEY", request_fn=fake_get)
    assert "Authorization" not in seen


def test_fetch_available_models_env_name_validation():
    assert is_valid_env_var_name("OPENCODE_API_KEY")
    assert is_valid_env_var_name("OPENROUTER_API_KEY")
    assert not is_valid_env_var_name("sk-" + "a" * 48)
    assert not is_valid_env_var_name("ghp_" + "a" * 36)


def test_fetch_available_models_403_without_env_var_explains_auth(monkeypatch):
    from jaspervoice.postprocessing import fetch_available_models

    monkeypatch.delenv("OPENCODE_API_KEY", raising=False)

    def fake_get(url, headers, timeout):
        raise urllib.error.HTTPError(url, 403, "Forbidden", None, None)

    with pytest.raises(PostProcessorError) as exc_info:
        fetch_available_models(
            "https://api.example.com",
            api_key_env="OPENCODE_API_KEY",
            request_fn=fake_get,
        )
    msg = str(exc_info.value)
    assert "403" in msg
    assert "OPENCODE_API_KEY" in msg
    assert "restart" in msg


def test_fetch_available_models_403_raw_key_does_not_leak_secret():
    from jaspervoice.postprocessing import fetch_available_models

    secret = "sk-" + "a" * 48

    def fake_get(url, headers, timeout):
        raise urllib.error.HTTPError(url, 403, "Forbidden", None, None)

    with pytest.raises(PostProcessorError) as exc_info:
        fetch_available_models(
            "https://api.example.com",
            api_key_env=secret,
            request_fn=fake_get,
        )
    msg = str(exc_info.value)
    assert secret not in msg
    assert "not the key itself" in msg


def test_fetch_available_models_empty_endpoint_raises():
    from jaspervoice.postprocessing import fetch_available_models

    with pytest.raises(PostProcessorError):
        fetch_available_models("   ")


def test_fetch_available_models_bad_json_raises():
    from jaspervoice.postprocessing import fetch_available_models

    with pytest.raises(PostProcessorError):
        fetch_available_models("http://x", request_fn=lambda u, h, t: b"not json")


def test_fetch_available_models_empty_list_raises():
    from jaspervoice.postprocessing import fetch_available_models

    with pytest.raises(PostProcessorError):
        fetch_available_models(
            "http://x", request_fn=lambda u, h, t: json.dumps({"data": []}).encode()
        )

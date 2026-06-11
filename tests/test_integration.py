"""Integration smoke: simulate press -> release cycle end-to-end without real hooks."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import time
import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from jaspervoice.app import App


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


def test_pipeline_runs_end_to_end(qt_app, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr("jaspervoice.config.load_config", lambda: {
        "hotkey": "ctrl+shift+space",
        "language": "pt",
        "model_size": "tiny",
        "compute_type": "int8",
        "device": "cpu",
        "sample_rate": 16000,
    })
    captured = []
    monkeypatch.setattr("jaspervoice.app.injection.inject_text", lambda t, settle_ms=30: captured.append(t) or True)

    from jaspervoice.transcription import TranscriptionResult
    monkeypatch.setattr("jaspervoice.app.Transcriber.transcribe", lambda self, audio, sample_rate=16000: TranscriptionResult(text="smoke test", language="en", duration=0.5))

    a = App()
    a.setup()

    fake_audio = (np.random.default_rng(0).normal(0, 0.01, 8000)).astype(np.float32)
    monkeypatch.setattr(a._recorder, "stop", lambda: fake_audio)

    a._on_press()
    a._on_release()

    deadline = time.monotonic() + 20.0
    while a._busy and time.monotonic() < deadline:
        qt_app.processEvents(QEventLoop.AllEvents, 100)

    assert a._busy is False
    a._shutdown()


def test_settings_apply_triggers_hot_reload(qt_app, tmp_path, monkeypatch):
    """When SettingsWindow emits configChanged, the App must update its
    internal cfg, restart the hotkey listener if the combo changed, and
    swap the transcriber if model/device/compute changed."""
    from jaspervoice.hotkey import parse_hotkey
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr("jaspervoice.config.load_config", lambda: {
        "hotkey": "ctrl+shift+space",
        "language": "pt",
        "model_size": "tiny",
        "compute_type": "int8",
        "device": "cpu",
        "sample_rate": 16000,
    })
    a = App()
    a.setup()
    try:
        # Record the initial hotkey listener combo
        assert a._hotkey is not None
        assert a._hotkey.combo == parse_hotkey("ctrl+shift+space")

        # Apply a new config with a different hotkey
        new_cfg = dict(a._cfg)
        new_cfg["hotkey"] = "ctrl+alt+r"
        a._on_config_changed(new_cfg)

        # Hotkey listener should be replaced
        assert a._hotkey is not None
        assert a._hotkey.combo == parse_hotkey("ctrl+alt+r")
        # Internal cfg updated
        assert a._cfg["hotkey"] == "ctrl+alt+r"
    finally:
        a._shutdown()


def test_overlay_mirrors_state_changes(qt_app, tmp_path, monkeypatch):
    """Press/cancel should propagate state to the overlay."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr("jaspervoice.config.load_config", lambda: {
        "hotkey": "ctrl+shift+space",
        "language": "pt",
        "model_size": "tiny",
        "compute_type": "int8",
        "device": "cpu",
        "sample_rate": 16000,
    })
    a = App()
    a.setup()
    try:
        assert a._overlay is not None
        assert a._overlay.state() == "idle"
        assert not a._overlay.isVisible()

        # Simulate press
        a._on_press()
        assert a._overlay.state() == "recording"
        assert a._overlay.isVisible()

        # Simulate cancel (short take)
        a._recorder.cancel()
        a._on_cancel()
        assert a._overlay.state() == "idle"
        # The redesigned overlay hides via a fade-out animation; force it to
        # completion so the synchronous visibility check is deterministic.
        a._overlay._opacity_anim.stop()
        a._overlay.setWindowOpacity(0.0)
        a._overlay._hide_after_fade()
        assert not a._overlay.isVisible()
    finally:
        a._shutdown()


def test_tray_settings_requested_opens_settings(qt_app, tmp_path, monkeypatch):
    """The tray's Settings... menu item must trigger settings.show()."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr("jaspervoice.config.load_config", lambda: {
        "hotkey": "ctrl+shift+space",
        "language": "pt",
        "model_size": "tiny",
        "compute_type": "int8",
        "device": "cpu",
        "sample_rate": 16000,
    })
    a = App()
    a.setup()
    try:
        assert a._settings is not None
        a._tray.settings_requested.emit()
        assert a._settings.isVisible()
    finally:
        a._shutdown()


def test_paste_delay_ms_reaches_inject_text(qt_app, tmp_path, monkeypatch):
    """TranscriptionWorker must call inject_text with settle_ms=configured value."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr("jaspervoice.config.load_config", lambda: {
        "hotkey": "ctrl+shift+space",
        "language": "pt",
        "model_size": "tiny",
        "compute_type": "int8",
        "device": "cpu",
        "sample_rate": 16000,
        "paste_delay_ms": 75,
        "min_recording_ms": 200,
    })
    captured_invocations = []
    monkeypatch.setattr("jaspervoice.app.injection.inject_text", lambda t, settle_ms=30: captured_invocations.append((t, settle_ms)) or True)

    from jaspervoice.transcription import TranscriptionResult
    monkeypatch.setattr("jaspervoice.app.Transcriber.transcribe", lambda self, audio, sample_rate=16000: TranscriptionResult(text="hello world", language="en", duration=0.5))

    a = App()
    a.setup()

    fake_audio = (np.random.default_rng(1).normal(0, 0.01, 8000)).astype(np.float32)
    monkeypatch.setattr(a._recorder, "stop", lambda: fake_audio)

    a._on_press()
    a._on_release()

    deadline = time.monotonic() + 20.0
    while a._busy and time.monotonic() < deadline:
        qt_app.processEvents(QEventLoop.AllEvents, 100)

    a._shutdown()

    assert len(captured_invocations) >= 1
    _text, settle_ms = captured_invocations[0]
    assert settle_ms == 75, f"Expected settle_ms=75, got {settle_ms}"
    assert _text == "hello world"


def test_language_changed_syncs_settings(qt_app, tmp_path, monkeypatch):
    """App._on_language_changed("en") must update SettingsWindow config to 'en'."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr("jaspervoice.config.load_config", lambda: {
        "hotkey": "ctrl+shift+space",
        "language": "pt",
        "model_size": "tiny",
        "compute_type": "int8",
        "device": "cpu",
        "sample_rate": 16000,
    })
    a = App()
    a.setup()
    try:
        assert a._settings is not None
        a._on_language_changed("en")
        assert a._cfg["language"] == "en"
        assert a._settings._cfg["language"] == "en"
        assert a._settings.lang_combo.currentData() == "en"
        assert a._settings.apply_btn.isEnabled() is False
    finally:
        a._shutdown()


def test_config_changed_syncs_tray_menu(qt_app, tmp_path, monkeypatch):
    """App._on_config_changed with model/device/language changes must rebuild tray menu."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr("jaspervoice.config.load_config", lambda: {
        "hotkey": "ctrl+shift+space",
        "language": "pt",
        "model_size": "tiny",
        "compute_type": "int8",
        "device": "cpu",
        "sample_rate": 16000,
    })
    a = App()
    a.setup()
    try:
        assert a._tray is not None
        new_cfg = dict(a._cfg)
        new_cfg["model_size"] = "base"
        new_cfg["device"] = "cuda"
        new_cfg["language"] = "en"
        a._on_config_changed(new_cfg)

        assert a._tray._cfg["model_size"] == "base"
        assert a._tray._cfg["device"] == "cuda"
        assert a._tray._cfg["language"] == "en"
    finally:
        a._shutdown()


def test_settings_update_config_does_not_mark_dirty(qt_app, tmp_path, monkeypatch):
    """SettingsWindow.update_config() must refresh UI without marking dirty."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr("jaspervoice.config.load_config", lambda: {
        "hotkey": "ctrl+shift+space",
        "language": "pt",
        "model_size": "tiny",
        "compute_type": "int8",
        "device": "cpu",
        "sample_rate": 16000,
    })
    a = App()
    a.setup()
    try:
        changed_signal_fired = []
        a._settings.configChanged.connect(lambda cfg: changed_signal_fired.append(cfg))

        new_cfg = dict(a._cfg)
        new_cfg["language"] = "en"
        new_cfg["model_size"] = "base"
        a._settings.update_config(new_cfg)

        assert a._settings._dirty is False
        assert a._settings.apply_btn.isEnabled() is False
        assert len(changed_signal_fired) == 0
    finally:
        a._shutdown()


def test_postprocessor_injects_final_text(qt_app, tmp_path, monkeypatch):
    """Pipeline must call inject_text with the text returned by the postprocessor."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr("jaspervoice.config.load_config", lambda: {
        "hotkey": "ctrl+shift+space",
        "language": "pt",
        "model_size": "tiny",
        "compute_type": "int8",
        "device": "cpu",
        "sample_rate": 16000,
        "paste_delay_ms": 30,
        "min_recording_ms": 200,
        "output_mode": "clean",
        "post_processing_enabled": True,
        "post_processing_provider": "none",
    })
    captured = []
    monkeypatch.setattr("jaspervoice.app.injection.inject_text", lambda t, settle_ms=30: captured.append(t) or True)

    from jaspervoice.transcription import TranscriptionResult
    monkeypatch.setattr("jaspervoice.app.Transcriber.transcribe", lambda self, audio, sample_rate=16000: TranscriptionResult(text="hello world", language="en", duration=0.5))

    a = App()
    a.setup()

    fake_audio = (np.random.default_rng(2).normal(0, 0.01, 8000)).astype(np.float32)
    monkeypatch.setattr(a._recorder, "stop", lambda: fake_audio)

    a._on_press()
    a._on_release()

    deadline = time.monotonic() + 20.0
    while a._busy and time.monotonic() < deadline:
        qt_app.processEvents(QEventLoop.AllEvents, 100)

    a._shutdown()

    assert len(captured) >= 1
    assert captured[0] == "hello world"


def test_postprocessor_failure_falls_back_to_raw_text(qt_app, tmp_path, monkeypatch):
    """When the postprocessor raises PostProcessorError, the pipeline must
    inject the raw transcription text and NOT leave _busy stuck."""
    from jaspervoice.postprocessing import PostProcessorError

    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr("jaspervoice.config.load_config", lambda: {
        "hotkey": "ctrl+shift+space",
        "language": "pt",
        "model_size": "tiny",
        "compute_type": "int8",
        "device": "cpu",
        "sample_rate": 16000,
        "paste_delay_ms": 30,
        "min_recording_ms": 200,
        "output_mode": "clean",
        "post_processing_enabled": True,
        "post_processing_provider": "none",
    })
    captured = []
    monkeypatch.setattr("jaspervoice.app.injection.inject_text", lambda t, settle_ms=30: captured.append(t) or True)

    from jaspervoice.transcription import TranscriptionResult
    monkeypatch.setattr("jaspervoice.app.Transcriber.transcribe", lambda self, audio, sample_rate=16000: TranscriptionResult(text="raw dictation", language="en", duration=0.5))

    a = App()
    a.setup()

    monkeypatch.setattr(a._worker._postprocessor, "process", lambda text, mode="raw": (_ for _ in ()).throw(PostProcessorError("boom")))

    fake_audio = (np.random.default_rng(3).normal(0, 0.01, 8000)).astype(np.float32)
    monkeypatch.setattr(a._recorder, "stop", lambda: fake_audio)

    a._on_press()
    a._on_release()

    deadline = time.monotonic() + 20.0
    while a._busy and time.monotonic() < deadline:
        qt_app.processEvents(QEventLoop.AllEvents, 100)

    a._shutdown()

    assert len(captured) >= 1
    assert captured[0] == "raw dictation"
    assert a._busy is False


def test_fake_postprocessor_injects_final_text(qt_app, tmp_path, monkeypatch):
    """With a fake postprocessor returning 'final dictation', inject_text gets that text."""
    from jaspervoice.postprocessing import PostProcessResult

    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr("jaspervoice.config.load_config", lambda: {
        "hotkey": "ctrl+shift+space",
        "language": "pt",
        "model_size": "tiny",
        "compute_type": "int8",
        "device": "cpu",
        "sample_rate": 16000,
        "paste_delay_ms": 30,
        "min_recording_ms": 200,
        "output_mode": "prompt",
        "post_processing_enabled": True,
        "post_processing_provider": "opencode",
        "opencode_base_url": "https://fake.example.com",
    })
    captured = []
    monkeypatch.setattr("jaspervoice.app.injection.inject_text", lambda t, settle_ms=30: captured.append(t) or True)

    from jaspervoice.transcription import TranscriptionResult
    monkeypatch.setattr("jaspervoice.app.Transcriber.transcribe", lambda self, audio, sample_rate=16000: TranscriptionResult(text="raw dictation", language="en", duration=0.5))

    a = App()
    a.setup()

    monkeypatch.setattr(a._worker._postprocessor, "process", lambda text, mode="raw": PostProcessResult(
        text="final dictation", provider="fake", mode="prompt", model="fake-model", latency_ms=1
    ))

    fake_audio = (np.random.default_rng(4).normal(0, 0.01, 8000)).astype(np.float32)
    monkeypatch.setattr(a._recorder, "stop", lambda: fake_audio)

    a._on_press()
    a._on_release()

    deadline = time.monotonic() + 20.0
    while a._busy and time.monotonic() < deadline:
        qt_app.processEvents(QEventLoop.AllEvents, 100)

    a._shutdown()

    assert len(captured) >= 1
    assert captured[0] == "final dictation"


def test_postprocessor_runtime_error_falls_back_to_raw_text(qt_app, tmp_path, monkeypatch):
    """Any exception from postprocessor (not just PostProcessorError) must
    fall back to raw_text without leaving _busy stuck."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr("jaspervoice.config.load_config", lambda: {
        "hotkey": "ctrl+shift+space",
        "language": "pt",
        "model_size": "tiny",
        "compute_type": "int8",
        "device": "cpu",
        "sample_rate": 16000,
        "paste_delay_ms": 30,
        "min_recording_ms": 200,
        "output_mode": "clean",
        "post_processing_enabled": True,
        "post_processing_provider": "opencode",
        "opencode_base_url": "https://fake.example.com",
    })
    captured = []
    monkeypatch.setattr("jaspervoice.app.injection.inject_text", lambda t, settle_ms=30: captured.append(t) or True)

    from jaspervoice.transcription import TranscriptionResult
    monkeypatch.setattr("jaspervoice.app.Transcriber.transcribe", lambda self, audio, sample_rate=16000: TranscriptionResult(text="raw dictation", language="en", duration=0.5))

    a = App()
    a.setup()

    monkeypatch.setattr(a._worker._postprocessor, "process", lambda text, mode="raw": (_ for _ in ()).throw(RuntimeError("unexpected crash")))

    fake_audio = (np.random.default_rng(5).normal(0, 0.01, 8000)).astype(np.float32)
    monkeypatch.setattr(a._recorder, "stop", lambda: fake_audio)

    a._on_press()
    a._on_release()

    deadline = time.monotonic() + 20.0
    while a._busy and time.monotonic() < deadline:
        qt_app.processEvents(QEventLoop.AllEvents, 100)

    a._shutdown()

    assert len(captured) >= 1
    assert captured[0] == "raw dictation"
    assert a._busy is False


def test_dictionary_applied_before_injection(qt_app, tmp_path, monkeypatch):
    """Dictionary must transform raw_text before injection."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr("jaspervoice.config.load_config", lambda: {
        "hotkey": "ctrl+shift+space",
        "language": "pt",
        "model_size": "tiny",
        "compute_type": "int8",
        "device": "cpu",
        "sample_rate": 16000,
        "paste_delay_ms": 30,
        "min_recording_ms": 200,
        "output_mode": "raw",
        "post_processing_enabled": False,
        "post_processing_provider": "none",
        "dictionary": [
            {"phrase": "use effect", "replacement": "useEffect"},
            {"phrase": "fast api", "replacement": "FastAPI"},
        ],
    })
    captured = []
    monkeypatch.setattr("jaspervoice.app.injection.inject_text", lambda t, settle_ms=30: captured.append(t) or True)

    from jaspervoice.transcription import TranscriptionResult
    monkeypatch.setattr("jaspervoice.app.Transcriber.transcribe", lambda self, audio, sample_rate=16000: TranscriptionResult(text="use effect with fast api", language="en", duration=0.5))

    a = App()
    a.setup()

    fake_audio = (np.random.default_rng(6).normal(0, 0.01, 8000)).astype(np.float32)
    monkeypatch.setattr(a._recorder, "stop", lambda: fake_audio)

    a._on_press()
    a._on_release()

    deadline = time.monotonic() + 20.0
    while a._busy and time.monotonic() < deadline:
        qt_app.processEvents(QEventLoop.AllEvents, 100)

    a._shutdown()

    assert len(captured) >= 1
    assert captured[0] == "useEffect with FastAPI"


def test_dictionary_runs_before_postprocessing(qt_app, tmp_path, monkeypatch):
    """Postprocessor must receive dictionary-corrected text, not raw text."""
    pp_received = []

    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("OPENCODE_API_KEY", "test-key")
    monkeypatch.setattr("jaspervoice.config.load_config", lambda: {
        "hotkey": "ctrl+shift+space",
        "language": "pt",
        "model_size": "tiny",
        "compute_type": "int8",
        "device": "cpu",
        "sample_rate": 16000,
        "paste_delay_ms": 30,
        "min_recording_ms": 200,
        "output_mode": "prompt",
        "post_processing_enabled": True,
        "post_processing_provider": "opencode",
        "opencode_base_url": "https://fake.example.com",
        "dictionary": [
            {"phrase": "use effect", "replacement": "useEffect"},
        ],
    })
    captured = []
    monkeypatch.setattr("jaspervoice.app.injection.inject_text", lambda t, settle_ms=30: captured.append(t) or True)

    from jaspervoice.transcription import TranscriptionResult
    monkeypatch.setattr("jaspervoice.app.Transcriber.transcribe", lambda self, audio, sample_rate=16000: TranscriptionResult(text="use effect here", language="en", duration=0.5))

    from jaspervoice.postprocessing import PostProcessResult

    a = App()
    a.setup()

    monkeypatch.setattr(a._worker._postprocessor, "process", lambda text, mode="raw": [
        pp_received.append(text),
        PostProcessResult(text=f"Final: {text}", provider="opencode", mode="prompt", model="fast", latency_ms=1),
    ][1])

    fake_audio = (np.random.default_rng(7).normal(0, 0.01, 8000)).astype(np.float32)
    monkeypatch.setattr(a._recorder, "stop", lambda: fake_audio)

    a._on_press()
    a._on_release()

    deadline = time.monotonic() + 20.0
    while a._busy and time.monotonic() < deadline:
        qt_app.processEvents(QEventLoop.AllEvents, 100)

    a._shutdown()

    assert pp_received == ["useEffect here"]
    assert captured == ["Final: useEffect here"]


def test_postprocessor_failure_preserves_dictionary_text(qt_app, tmp_path, monkeypatch):
    """When postprocessor fails, dictionary-corrected text is still injected."""
    from jaspervoice.postprocessing import PostProcessorError

    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr("jaspervoice.config.load_config", lambda: {
        "hotkey": "ctrl+shift+space",
        "language": "pt",
        "model_size": "tiny",
        "compute_type": "int8",
        "device": "cpu",
        "sample_rate": 16000,
        "paste_delay_ms": 30,
        "min_recording_ms": 200,
        "output_mode": "clean",
        "post_processing_enabled": True,
        "post_processing_provider": "opencode",
        "opencode_base_url": "https://fake.example.com",
        "dictionary": [
            {"phrase": "use effect", "replacement": "useEffect"},
        ],
    })
    captured = []
    monkeypatch.setattr("jaspervoice.app.injection.inject_text", lambda t, settle_ms=30: captured.append(t) or True)

    from jaspervoice.transcription import TranscriptionResult
    monkeypatch.setattr("jaspervoice.app.Transcriber.transcribe", lambda self, audio, sample_rate=16000: TranscriptionResult(text="use effect", language="en", duration=0.5))

    a = App()
    a.setup()

    monkeypatch.setattr(a._worker._postprocessor, "process", lambda text, mode="raw": (_ for _ in ()).throw(PostProcessorError("api down")))

    fake_audio = (np.random.default_rng(8).normal(0, 0.01, 8000)).astype(np.float32)
    monkeypatch.setattr(a._recorder, "stop", lambda: fake_audio)

    a._on_press()
    a._on_release()

    deadline = time.monotonic() + 20.0
    while a._busy and time.monotonic() < deadline:
        qt_app.processEvents(QEventLoop.AllEvents, 100)

    a._shutdown()

    assert len(captured) >= 1
    assert captured[0] == "useEffect"
    assert a._busy is False


def test_worker_signal_handlers_run_on_main_thread(qt_app, tmp_path, monkeypatch):
    """Worker signal handlers must execute on the Qt main thread, not the worker thread."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("OPENCODE_API_KEY", "test-key")
    monkeypatch.setattr("jaspervoice.config.load_config", lambda: {
        "hotkey": "ctrl+shift+space",
        "language": "pt",
        "model_size": "tiny",
        "compute_type": "int8",
        "device": "cpu",
        "sample_rate": 16000,
        "paste_delay_ms": 30,
        "min_recording_ms": 200,
        "output_mode": "raw",
        "post_processing_enabled": False,
        "post_processing_provider": "none",
        "dictionary": [],
    })
    monkeypatch.setattr("jaspervoice.app.injection.inject_text", lambda t, settle_ms=30: True)

    from jaspervoice.transcription import TranscriptionResult
    monkeypatch.setattr("jaspervoice.app.Transcriber.transcribe", lambda self, audio, sample_rate=16000: TranscriptionResult(text="smoke", language="en", duration=0.5))

    from PySide6.QtCore import QThread
    handler_threads = []

    a = App()
    a.setup()

    main_thread = a._qt.thread()

    original_finished = a._on_worker_finished
    def tracking_finished(text):
        handler_threads.append(QThread.currentThread())
        original_finished(text)
    a._on_worker_finished = tracking_finished

    fake_audio = (np.random.default_rng(9).normal(0, 0.01, 8000)).astype(np.float32)
    monkeypatch.setattr(a._recorder, "stop", lambda: fake_audio)

    a._on_press()
    a._on_release()

    deadline = time.monotonic() + 20.0
    while a._busy and time.monotonic() < deadline:
        qt_app.processEvents(QEventLoop.AllEvents, 100)

    a._shutdown()

    assert len(handler_threads) >= 1
    for ht in handler_threads:
        assert ht is main_thread, f"Handler ran on {ht}, expected main thread {main_thread}"

"""JasperVoice main app — wires Recorder, Transcriber, HotkeyListener, and Tray.

Pipeline:
    hotkey press   -> recorder.start()   -> tray.set_state("recording")
    hotkey release -> recorder.stop()    -> tray.set_state("processing")
                  -> worker thread: transcribe(audio) -> inject_text(text)
                  -> tray.set_state("idle")
                  -> on error: tray.set_state("error") briefly, then idle
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from typing import Optional

# On Windows, use the default QPA. Allow override via env for headless tests.
os.environ.setdefault("QT_QPA_PLATFORM", "")

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtWidgets import QApplication

from . import config as cfg_mod
from . import injection
from . import sounds
from .audio import Recorder, RecorderError
from .dictionary import DeveloperDictionary
from .history import TranscriptionHistory
from .hotkey import HotkeyListener, parse_hotkey
from .overlay import RecordingOverlay
from .postprocessing import (
    PostProcessor,
    PostProcessorError,
    NoopPostProcessor,
    OpenCodePostProcessor,
)
from .single_instance import SingleInstance
from .theme import apply_theme
from .transcription import Transcriber, TranscriberError
from .tray import TrayController
from .ui import SettingsWindow

log = logging.getLogger(__name__)


class _LevelBridge(QObject):
    """QObject that lives on the Qt main thread. The audio thread emits
    `levels` through it; the queued connection marshals the band data to
    the main thread where the overlay can repaint safely."""

    levels = Signal(list)


class TranscriptionWorker(QObject):
    """Runs the (transcribe + post-process + inject) pipeline off the Qt event loop."""

    finished = Signal(str)     # injected text (or empty)
    test_result = Signal(str)  # transcribed text for a test take (not injected)
    failed = Signal(str)       # error message
    state = Signal(str)        # state for the tray

    def __init__(
        self,
        transcriber: Transcriber,
        paste_delay_ms: int = 30,
        postprocessor: Optional[PostProcessor] = None,
        output_mode: str = "raw",
        post_processing_enabled: bool = False,
        dictionary: Optional[DeveloperDictionary] = None,
        warmup: bool = True,
    ):
        super().__init__()
        self._transcriber = transcriber
        self._paste_delay_ms = paste_delay_ms
        self._postprocessor: PostProcessor = postprocessor or NoopPostProcessor()
        self._output_mode = output_mode
        self._post_processing_enabled = post_processing_enabled
        self._dictionary: DeveloperDictionary = dictionary or DeveloperDictionary()
        self._warmup = warmup
        self._pending: Optional[tuple] = None
        self._stop = False
        self._lock = threading.Lock()
        self._cv = threading.Condition(self._lock)

    def submit(self, audio, sample_rate: int, inject: bool = True) -> None:
        """Queue a take. `inject=False` runs the same pipeline but emits
        `test_result` instead of pasting into the focused window (used by the
        settings window's Test dictation button)."""
        with self._cv:
            if self._stop:
                return
            self._pending = (audio, sample_rate, inject)
            self._cv.notify_all()

    def stop(self) -> None:
        with self._cv:
            self._stop = True
            self._cv.notify_all()

    def _wait_for_task(self):
        with self._cv:
            while self._pending is None and not self._stop:
                self._cv.wait()
            if self._stop:
                return None
            return self._pending

    def run(self) -> None:
        # Warm up the Whisper model as the worker thread's first action, before
        # blocking on the task queue. This loads the model right after startup
        # so the first dictation doesn't pay the ~2-5s model-load cost.
        with self._cv:
            already_stopped = self._stop
        if not already_stopped and self._warmup:
            try:
                self._transcriber._ensure_loaded()
                log.info(
                    "Model warmup complete: loaded on device=%s",
                    self._transcriber.resolved_device,
                )
            except Exception as e:
                log.warning("Model warmup failed: %s. Will retry on first transcription.", e)
        while True:
            pending = self._wait_for_task()
            if pending is None:
                return
            audio, sample_rate, inject = pending
            try:
                self.state.emit("processing")
                result = self._transcriber.transcribe(audio, sample_rate=sample_rate)
                raw_text = result.text.strip()
                if not raw_text:
                    (self.finished if inject else self.test_result).emit("")
                    continue

                dict_text = raw_text
                try:
                    dict_text = self._dictionary.apply(raw_text)
                except Exception as e:
                    log.warning("Dictionary apply failed: %s. Continuing with raw text.", e)

                final_text = dict_text
                if self._post_processing_enabled:
                    try:
                        pp_result = self._postprocessor.process(dict_text, mode=self._output_mode)
                        final_text = pp_result.text
                    except PostProcessorError as e:
                        log.warning("Post-processing failed: %s. Falling back to dictionary text.", e)
                    except Exception as e:
                        log.warning("Post-processing unexpected error: %s. Falling back to dictionary text.", e)

                if inject:
                    injection.inject_text(final_text, settle_ms=self._paste_delay_ms)
                    self.finished.emit(final_text)
                else:
                    self.test_result.emit(final_text)
            except (TranscriberError, RecorderError) as e:
                log.exception("Pipeline error")
                self.failed.emit(str(e))
            except Exception as e:  # last-resort safety net
                log.exception("Unexpected error")
                self.failed.emit(f"Unexpected: {e}")
            finally:
                with self._cv:
                    self._pending = None


class App(QObject):
    def __init__(self):
        super().__init__()
        self._cfg = cfg_mod.load_config()
        self._level_bridge = _LevelBridge()
        self._recorder = Recorder(
            sample_rate=int(self._cfg["sample_rate"]),
            device=self._resolve_input_device(self._cfg),
            level_callback=lambda bands: self._level_bridge.levels.emit(bands),
        )
        self._transcriber = Transcriber(
            model_size=self._cfg["model_size"],
            device=self._cfg["device"],
            compute_type=self._cfg["compute_type"],
            language=self._cfg["language"],
            download_root=cfg_mod.get_models_dir(),
        )
        self._qt: Optional[QApplication] = None
        self._tray: Optional[TrayController] = None
        self._hotkey: Optional[HotkeyListener] = None
        self._worker_thread: Optional[QThread] = None
        self._worker: Optional[TranscriptionWorker] = None
        self._error_timer: Optional[QTimer] = None
        self._overlay: Optional[RecordingOverlay] = None
        self._settings: Optional[SettingsWindow] = None
        self._busy = False
        self._hotkey_mode = self._cfg.get("hotkey_mode", "push_to_talk")
        self._history = TranscriptionHistory()
        self._recording_start: Optional[float] = None
        self._last_duration_s: float = 0.0
        self._overlay_enabled = bool(self._cfg.get("show_overlay", True))
        self._last_state = "idle"
        # Test dictation (settings window "Test dictation" button): records a
        # short take and runs the real pipeline with injection disabled.
        self._test_pending = False
        self._test_timer: Optional[QTimer] = None
        # Hold the single-instance mutex for the process lifetime. Acquired in
        # run(); kept as an attribute so the OS keeps the kernel object alive
        # until we exit.
        self._instance_guard: Optional["SingleInstance"] = None
        # Background startup update-check thread/worker (created lazily).
        self._startup_check_thread: Optional[QThread] = None
        self._startup_check_worker: Optional[QObject] = None

    @staticmethod
    def _resolve_input_device(cfg: dict) -> Optional[str]:
        device = str(cfg.get("input_device", "default"))
        return None if device == "default" else device

    def _set_state(self, state: str) -> None:
        """Mirror a state to tray, overlay (if enabled), and settings window,
        and play the configured audible cue on state transitions."""
        if state != self._last_state:
            self._last_state = state
            sounds.play_state_cue(state, str(self._cfg.get("sound_feedback", "off")))
        if self._tray is not None:
            self._tray.set_state(state)
        if self._overlay is not None and self._overlay_enabled:
            self._overlay.set_state(state)
        if self._settings is not None:
            self._settings.set_app_state(state)

    def _state_is(self, state: str) -> bool:
        """Check if current overlay state matches."""
        if self._overlay is not None:
            return self._overlay.state() == state
        return False

    @Slot(list)
    def _on_levels_updated(self, bands: list) -> None:
        if self._overlay is not None:
            self._overlay.levels_updated.emit(bands)

    @staticmethod
    def _build_postprocessor(cfg: dict) -> PostProcessor:
        provider = cfg.get("post_processing_provider", "none")
        if provider == "opencode":
            return OpenCodePostProcessor(
                base_url=cfg.get("opencode_base_url", ""),
                api_key_env=cfg.get("opencode_api_key_env", "OPENCODE_API_KEY"),
                fast_model=cfg.get("opencode_fast_model", "DeepSeek V4 Flash"),
                smart_model=cfg.get("opencode_smart_model", "Qwen3.7 Max"),
                timeout_s=int(cfg.get("opencode_timeout_s", 20)),
            )
        return NoopPostProcessor()

    # ----- Hotkey callbacks -----
    def _on_press(self) -> None:
        if self._busy:
            log.debug("Ignoring press: pipeline busy")
            return
        try:
            self._recorder.start()
            self._busy = True
            self._recording_start = time.monotonic()
            self._set_state("recording")
            if self._tray and self._hotkey_mode == "toggle":
                self._tray.set_status_detail("Press again to stop")
        except RecorderError as e:
            log.error("Cannot start recording: %s", e)
            self._set_state("error")
            if self._tray:
                self._tray.set_status_detail(str(e))
            self._schedule_idle_after_error()

    def _on_release(self) -> None:
        if not self._busy or self._test_pending:
            return
        try:
            audio = self._recorder.stop()
        except Exception as e:
            log.exception("Stop recording failed")
            self._busy = False
            self._set_state("error")
            if self._tray:
                self._tray.set_status_detail(str(e))
            self._schedule_idle_after_error()
            return
        duration = Recorder.duration_seconds(audio, int(self._cfg["sample_rate"]))
        if audio.size == 0 or duration < (self._cfg.get("min_recording_ms", 200) / 1000.0):
            log.info("Discarding %.2fs take (too short)", duration)
            self._busy = False
            self._recording_start = None
            self._set_state("idle")
            return
        self._last_duration_s = duration
        if self._worker is not None:
            self._worker.submit(audio, int(self._cfg["sample_rate"]))

    def _on_cancel(self) -> None:
        if self._test_pending:
            return
        if self._recorder.is_active:
            self._recorder.cancel()
        self._busy = False
        self._recording_start = None
        self._set_state("idle")

    # ----- Test dictation (settings window) -----
    def _on_test_dictation(self) -> None:
        """Record ~4s and run the real pipeline without injecting the result."""
        if self._busy:
            if self._settings is not None:
                self._settings.show_test_result("Pipeline busy — finish the current take first.")
            return
        try:
            self._recorder.start()
        except RecorderError as e:
            if self._settings is not None:
                self._settings.show_test_result(f"Microphone error: {e}")
            return
        self._busy = True
        self._test_pending = True
        self._set_state("recording")
        if self._test_timer is not None:
            self._test_timer.start(4000)

    def _finish_test_dictation(self) -> None:
        if not self._test_pending:
            return
        try:
            audio = self._recorder.stop()
        except Exception as e:
            log.exception("Test recording stop failed")
            self._busy = False
            self._test_pending = False
            self._set_state("idle")
            if self._settings is not None:
                self._settings.show_test_result(f"Recording failed: {e}")
            return
        if audio.size == 0:
            self._busy = False
            self._test_pending = False
            self._set_state("idle")
            if self._settings is not None:
                self._settings.show_test_result("No audio captured — check the input device.")
            return
        if self._worker is not None:
            self._worker.submit(audio, int(self._cfg["sample_rate"]), inject=False)

    @Slot(str)
    def _on_worker_test_result(self, text: str) -> None:
        self._busy = False
        self._test_pending = False
        self._set_state("idle")
        if self._settings is not None:
            self._settings.show_test_result(text or "(no speech detected)")

    def _runtime_info(self) -> dict:
        """Live info for the settings window status areas (UI thread only)."""
        info: dict = {}
        if self._transcriber is not None:
            info["resolved_device"] = self._transcriber.resolved_device
            info["model_loaded"] = self._transcriber.is_loaded
        if self._last_duration_s:
            info["last_duration_s"] = self._last_duration_s
        return info

    # ----- Worker signals -----
    @Slot(str)
    def _on_worker_finished(self, text: str) -> None:
        self._busy = False
        self._recording_start = None
        # Show "Sent!" briefly before returning to idle
        self._set_state("send")
        if text:
            try:
                self._history.add(text, duration_s=self._last_duration_s, mode=self._hotkey_mode)
            except Exception as e:
                log.warning("Failed to add to history: %s", e)
        if self._tray:
            if text:
                self._tray.set_status_detail(f"Last: {text[:40]}{'…' if len(text) > 40 else ''}")
            else:
                self._tray.set_status_detail("(no speech detected)")
        # Return to idle after 700ms
        if self._qt is not None:
            QTimer.singleShot(700, lambda: self._set_state("idle") if self._state_is("send") else None)

    @Slot(str)
    def _on_worker_failed(self, msg: str) -> None:
        self._busy = False
        if self._test_pending:
            self._test_pending = False
            if self._settings is not None:
                self._settings.show_test_result(f"Error: {msg}")
        self._set_state("error")
        if self._tray:
            short = msg if len(msg) < 80 else msg[:77] + "…"
            self._tray.set_status_detail(short)
        self._schedule_idle_after_error()

    @Slot(str)
    def _on_worker_state(self, state: str) -> None:
        if state == "processing":
            self._set_state("processing")

    def _schedule_idle_after_error(self) -> None:
        if self._qt is None:
            return
        # _error_timer is created in setup() on the main thread; just start it.
        if self._error_timer is not None:
            self._error_timer.start(3000)

    def _clear_error_state(self) -> None:
        # Only return to idle if we're still in error (user may have triggered
        # another action in the meantime).
        if self._tray is not None and self._tray._state == "error":
            self._set_state("idle")
        if self._overlay is not None and self._overlay.state() == "error":
            self._set_state("idle")

    # ----- Setup / lifecycle -----
    def setup(self) -> None:
        self._qt = QApplication.instance() or QApplication(sys.argv)
        apply_theme(self._qt)
        self._qt.setQuitOnLastWindowClosed(False)
        self._qt.setApplicationName("JasperVoice")

        from .assets import icon_path
        _icon_file = icon_path()
        if _icon_file:
            from PySide6.QtGui import QIcon
            self._qt.setWindowIcon(QIcon(_icon_file))

        self._tray = TrayController(self._qt, cfg=self._cfg)
        self._tray.quit_requested.connect(self._shutdown)
        self._tray.language_changed.connect(self._on_language_changed)
        self._tray.settings_requested.connect(self._show_settings)
        self._tray.stats_requested.connect(self._show_stats)
        self._tray.update_check_requested.connect(self._check_for_updates)

        # Settings window (constructed before overlay so overlay can connect
        # to it for the "Settings..." context menu).
        self._settings = SettingsWindow(self._cfg, history=self._history)
        self._settings.configChanged.connect(self._on_config_changed)
        self._settings.testDictationRequested.connect(self._on_test_dictation)
        self._settings.set_runtime_provider(self._runtime_info)

        # Floating recording indicator.
        self._overlay = RecordingOverlay()
        self._overlay.set_position(str(self._cfg.get("overlay_position", "bottom_right")))
        self._overlay.clicked.connect(self._show_settings)
        self._overlay.settings_requested.connect(self._show_settings)
        self._overlay.quit_requested.connect(self._shutdown)

        # Forward live audio band levels (emitted from the audio thread) to the
        # overlay's spectrum visualizer on the main thread.
        self._level_bridge.levels.connect(
            self._on_levels_updated, Qt.ConnectionType.QueuedConnection
        )

        # Error auto-recovery timer (created on the main thread to avoid
        # the cross-thread warning seen when constructing QTimer lazily).
        self._error_timer = QTimer()
        self._error_timer.setSingleShot(True)
        self._error_timer.timeout.connect(self._clear_error_state)

        # Test-dictation stop timer (main thread, single shot).
        self._test_timer = QTimer()
        self._test_timer.setSingleShot(True)
        self._test_timer.timeout.connect(self._finish_test_dictation)

        # Worker on its own QThread so the Qt loop stays responsive.
        self._worker_thread = QThread()
        self._worker = TranscriptionWorker(
            self._transcriber,
            paste_delay_ms=int(self._cfg.get("paste_delay_ms", 15)),
            postprocessor=self._build_postprocessor(self._cfg),
            output_mode=self._cfg.get("output_mode", "raw"),
            post_processing_enabled=bool(self._cfg.get("post_processing_enabled", False)),
            dictionary=DeveloperDictionary(self._cfg.get("dictionary", [])),
            warmup=bool(self._cfg.get("warmup_on_launch", True)),
        )
        self._worker.moveToThread(self._worker_thread)
        self._worker_thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_worker_finished, Qt.ConnectionType.QueuedConnection)
        self._worker.test_result.connect(self._on_worker_test_result, Qt.ConnectionType.QueuedConnection)
        self._worker.failed.connect(self._on_worker_failed, Qt.ConnectionType.QueuedConnection)
        self._worker.state.connect(self._on_worker_state, Qt.ConnectionType.QueuedConnection)
        self._worker_thread.start()

        self._hotkey = HotkeyListener(
            hotkey=self._cfg["hotkey"],
            on_press=self._on_press,
            on_release=self._on_release,
            on_cancel=self._on_cancel,
            hotkey_mode=self._hotkey_mode,
        )
        try:
            self._hotkey.start()
        except Exception as e:
            self._set_state("error")
            if self._tray:
                self._tray.set_status_detail(
                    f"Hotkey hook failed: {e}. Try running as Administrator."
                )
            # Do not raise: tray menu still works for quit.

        # Note: we deliberately do not install a SIGINT handler. On Windows the
        # default Ctrl+C handling works fine for console runs, and installing
        # a custom handler from the main thread can cause reentrant shutdown
        # issues if it fires while the event loop is mid-tear-down.

    def _startup_update_check(self) -> None:
        """Background, failure-safe update check. Notifies via tray only if an
        update is available; never opens a window or blocks the UI."""
        try:
            from .ui import _CheckWorker
        except Exception:
            return
        repo = str(self._cfg.get("update_repo") or "")
        thread = QThread()
        worker = _CheckWorker(repo)
        worker.moveToThread(thread)
        # Keep references so they aren't garbage-collected mid-run.
        self._startup_check_thread = thread
        self._startup_check_worker = worker

        def _done(info) -> None:
            thread.quit()
            if info is not None and self._tray is not None:
                self._tray.show_message(
                    "JasperVoice update available",
                    f"Version {info.version} is ready. Open the tray → "
                    "Check for updates to install.",
                )

        def _error(_msg: str) -> None:
            thread.quit()  # soft-fail: stay quiet, app keeps running

        thread.started.connect(worker.run)
        worker.done.connect(_done, Qt.ConnectionType.QueuedConnection)
        worker.error.connect(_error, Qt.ConnectionType.QueuedConnection)
        thread.start()

    def _on_language_changed(self, code: str) -> None:
        self._transcriber.set_language(code)
        self._cfg["language"] = code
        if self._settings is not None:
            self._settings.update_config(self._cfg)

    def _show_settings(self) -> None:
        if self._settings is None:
            return
        self._settings.show()
        self._settings.raise_()
        self._settings.activateWindow()

    def _show_stats(self) -> None:
        # Statistics now live in the main window (Overview tiles + History page).
        if self._settings is None:
            return
        self._settings.show_page("history")
        self._show_settings()

    # ----- Updates -----
    def _check_for_updates(self) -> None:
        """Manual update check from the tray. Fully failure-safe: any error is
        shown as a tray message and the app keeps running normally."""
        from .ui import UpdateDialog

        repo = str(self._cfg.get("update_repo") or "")
        dlg = UpdateDialog(repo=repo, parent=self._settings)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        # Keep a reference so it isn't garbage-collected while open.
        self._update_dialog = dlg

    def _on_config_changed(self, new_cfg: dict) -> None:
        """Apply a new config live. Hotkey listener is restarted; transcriber
        is recreated if model/device/compute changed; language is updated."""
        self._cfg = new_cfg

        # Hotkey hot-reload
        new_mode = new_cfg.get("hotkey_mode", "push_to_talk")
        if (
            self._hotkey is None
            or self._hotkey.combo != parse_hotkey(new_cfg["hotkey"])
            or self._hotkey._mode != new_mode
        ):
            try:
                if self._hotkey is not None:
                    self._hotkey.stop()
                self._hotkey = HotkeyListener(
                    hotkey=new_cfg["hotkey"],
                    on_press=self._on_press,
                    on_release=self._on_release,
                    on_cancel=self._on_cancel,
                    hotkey_mode=new_mode,
                )
                self._hotkey.start()
            except Exception as e:
                log.error("Hotkey hot-reload failed: %s", e)
                if self._tray:
                    self._tray.set_status_detail(f"Hotkey failed: {e}")
        self._hotkey_mode = new_mode

        # Language hot-update (cheap)
        if self._transcriber is not None:
            self._transcriber.set_language(new_cfg["language"])

        # Recreate transcriber if model/device/compute changed (model loads lazily)
        if (
            self._transcriber is None
            or self._transcriber._requested_model_size != new_cfg["model_size"]
            or self._transcriber._requested_device != new_cfg["device"]
            or self._transcriber._compute_type != new_cfg["compute_type"]
        ):
            self._transcriber = Transcriber(
                model_size=new_cfg["model_size"],
                device=new_cfg["device"],
                compute_type=new_cfg["compute_type"],
                language=new_cfg["language"],
                download_root=cfg_mod.get_models_dir(),
            )
            if self._worker is not None:
                # Swap the transcriber reference inside the worker.
                # The worker reads `self._transcriber` on each task, so the
                # next transcription will use the new model.
                self._worker._transcriber = self._transcriber

        # Update paste delay on the worker (cheap)
        if self._worker is not None:
            self._worker._paste_delay_ms = int(new_cfg.get("paste_delay_ms", 15))
            self._worker._dictionary = DeveloperDictionary(new_cfg.get("dictionary", []))

        # Update post-processing settings on the worker
        if self._worker is not None:
            self._worker._output_mode = new_cfg.get("output_mode", "raw")
            self._worker._post_processing_enabled = bool(new_cfg.get("post_processing_enabled", False))
            self._worker._postprocessor = self._build_postprocessor(new_cfg)

        # Input device (takes effect on the next recording)
        if self._recorder is not None:
            self._recorder.set_device(self._resolve_input_device(new_cfg))

        # Overlay visibility + corner
        self._overlay_enabled = bool(new_cfg.get("show_overlay", True))
        if self._overlay is not None:
            self._overlay.set_position(str(new_cfg.get("overlay_position", "bottom_right")))
            if not self._overlay_enabled:
                self._overlay.hide()

        # Windows startup registration
        self._apply_launch_at_login(bool(new_cfg.get("launch_at_login", False)))

        # NOTE adapter points (settings are persisted; runtime behavior pending):
        # - noise_gate_enabled: apply an RMS gate to `audio` in TranscriptionWorker.run
        #   before transcribe().
        # - warmup_on_launch: read at worker startup only; a change applies next launch.
        # sound_feedback is live: _set_state reads it from self._cfg on every transition.

        # Sync config to tray so its menu reflects current values
        if self._tray is not None:
            self._tray.update_config(new_cfg)

    @staticmethod
    def _apply_launch_at_login(enabled: bool) -> None:
        """Register/unregister JasperVoice in the per-user Windows Run key.

        Only effective in the frozen (installed) build — registering a dev
        `python -m jaspervoice` invocation at login would be wrong, so dev
        runs just log and skip.
        """
        if sys.platform != "win32":
            return
        if not getattr(sys, "frozen", False):
            log.info("launch_at_login=%s noted; registry not touched in dev runs", enabled)
            return
        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_SET_VALUE,
            )
            with key:
                if enabled:
                    winreg.SetValueEx(key, "JasperVoice", 0, winreg.REG_SZ, f'"{sys.executable}"')
                else:
                    try:
                        winreg.DeleteValue(key, "JasperVoice")
                    except FileNotFoundError:
                        pass
        except OSError as e:
            log.error("Could not update launch-at-login registration: %s", e)

    def _shutdown(self) -> None:
        if getattr(self, "_shutting_down", False):
            return
        self._shutting_down = True
        log.info("Shutting down")
        # Order matters: stop the keyboard hook FIRST (it can pump events),
        # then worker, then quit the Qt loop. This avoids deadlocks where
        # unhook_all() is called from inside a hook callback on Windows.
        try:
            if self._hotkey is not None:
                self._hotkey.stop()
                self._hotkey = None
        except Exception:
            pass
        try:
            if self._recorder is not None and self._recorder.is_active:
                self._recorder.cancel()
        except Exception:
            pass
        try:
            if self._worker is not None:
                self._worker.stop()
            if self._worker_thread is not None:
                self._worker_thread.quit()
                self._worker_thread.wait(2000)
                self._worker_thread = None
        except Exception:
            pass
        try:
            if self._startup_check_thread is not None:
                self._startup_check_thread.quit()
                self._startup_check_thread.wait(2000)
                self._startup_check_thread = None
                self._startup_check_worker = None
        except Exception:
            pass
        try:
            if self._overlay is not None:
                self._overlay.hide()
                self._overlay.deleteLater()
                self._overlay = None
        except Exception:
            pass
        try:
            if self._settings is not None:
                self._settings.shutdown_workers()
                self._settings.hide()
                self._settings.deleteLater()
                self._settings = None
        except Exception:
            pass
        try:
            if self._tray is not None:
                self._tray.shutdown()
        except Exception:
            pass
        if self._qt is not None:
            # Process any pending events, then quit. This avoids a deadlock
            # seen on Windows where unhook_all() leaves an event in the queue
            # that blocks the quit signal.
            try:
                self._qt.processEvents()
            except Exception:
                pass
            self._qt.quit()

    def run(self) -> int:
        # Single-instance guard: a second process would fight over the global
        # hotkey. If another instance already holds the mutex, surface a brief
        # tray notification (if possible) and exit cleanly.
        self._instance_guard = SingleInstance()
        if not self._instance_guard.acquire():
            log.warning("Another JasperVoice instance is already running; exiting.")
            try:
                self._notify_already_running()
            except Exception:
                pass
            return 0
        self.setup()
        log.info("JasperVoice running. Hotkey: %s", self._cfg["hotkey"])
        # Honor "start minimized to tray": when off, open the main window.
        if not self._cfg.get("start_minimized", True):
            self._show_settings()
        # Optional, non-blocking update check shortly after startup. Scheduled
        # here (not in setup()) so test harnesses that call setup() directly
        # never trigger a network check. Any failure is swallowed; it only
        # surfaces a tray notice when an update is actually available.
        if self._cfg.get("update_check_enabled", True):
            QTimer.singleShot(4000, self._startup_update_check)
        rc = self._qt.exec() if self._qt is not None else 1
        self._shutdown()
        return rc

    def _notify_already_running(self) -> None:
        """Best-effort balloon when a duplicate launch is blocked."""
        qt = QApplication.instance() or QApplication(sys.argv)
        from PySide6.QtWidgets import QSystemTrayIcon
        from PySide6.QtGui import QIcon

        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        from .assets import icon_path

        icon_file = icon_path()
        tray = QSystemTrayIcon(QIcon(icon_file) if icon_file else QIcon())
        tray.show()
        if tray.supportsMessages():
            tray.showMessage(
                "JasperVoice",
                "JasperVoice is already running (check the system tray).",
                QSystemTrayIcon.Information,
                3000,
            )
            qt.processEvents()


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    app = App()
    return app.run()


if __name__ == "__main__":
    raise SystemExit(main())

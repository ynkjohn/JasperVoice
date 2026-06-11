# Design: JasperVoice UI v1

## Context

The MVP shipped a tray-only PTT dictation app. Configuration was raw `config.json`; the only feedback during recording was a tray icon color change, which is easy to miss if the user's attention is on another window. This change adds a discoverable settings surface and a screen-space indicator that sits at the corner of the primary monitor.

User direction: technical minimalism in the spirit of OpenCode/Anthropic — dark only, monospace headings, orange accent (`#D97757`), thin borders, no shadows. No brutalist. No light theme in v1.

The existing `app.py` already has `_on_press`, `_on_release`, `_on_worker_finished`, `_on_worker_failed`, and `_on_worker_state` — all the integration points a UI needs to mirror. Tray already has four states with colored icons; the overlay will use the same state names so wiring is one line per state.

## Goals / Non-Goals

**Goals:**
- Settings window discoverable from tray menu and overlay click.
- Hot-reload of all settings (no restart), including the hotkey itself.
- Visible recording state at the corner of the primary monitor.
- Zero new runtime dependencies.
- Dark theme only in v1.

**Non-Goals:**
- Drag-to-reposition overlay.
- Light theme.
- i18n of the UI (en-US strings only).
- Waveform visualization.
- History of past transcriptions.
- Custom dictionary.
- Auto-launch on startup.
- Mic device picker (default device only).
- Toggle (hands-free) mode.

## Decisions

### D1. Dark-only theme in v1

OpenCode's reference site and Claude Code's docs are both dark-first. Adding a light theme doubles the QSS surface and the test matrix without clear user demand. Persisted in `config.json` as `"ui_theme": "dark"` so a future toggle can be added without breaking changes.

### D2. Single QSS string in `theme.py`, not a `.qss` file

QSS is <100 lines for v1. Inlining keeps the code grep-friendly and avoids an asset-loading failure mode. If it grows past 200 lines, split out `assets/style.qss` and load it in v1.1.

### D3. `setWindowOpacity` for fade/pulse, not `QGraphicsOpacityEffect`

Tested internally: `QGraphicsOpacityEffect` on a window with `WA_TranslucentBackground` paints black in some Windows DWM configurations. `setWindowOpacity(0.0..1.0)` is the official Qt API and works reliably. Simpler code: one property, one `QPropertyAnimation`, no extra effect object.

### D4. `windowOpacity` for the recording pulse, not for hide/show

Idle = `hide()` immediately (no fade), then re-`show()` when state leaves idle. Pulse = `QPropertyAnimation` on `windowOpacity` looping 0.4 ↔ 1.0 every 800ms, only while in `recording`. This avoids two concurrent animations fighting over the same property.

### D5. `QKeySequenceEdit` for hotkey capture, with bidirectional conversion to `keyboard` format

`QKeySequenceEdit` is the standard Qt widget for capturing key combos. It returns a `QKeySequence` like `Ctrl+Shift+R`. The `keyboard` library uses lowercase tokens joined by `+` like `ctrl+shift+r`. The conversion functions in `ui.py` handle this. Token-title mapping is explicit (`ctrl` → `Ctrl`, `pgup` → `PgUp`, `space` → `Space`) to avoid surprises with `title()` on unusual names.

### D6. Hotkey hot-reload via guard in `HotkeyListener.start()`

Previous behavior: `start()` while already running accumulated `keyboard.hook` callbacks. The new guard calls `stop()` if `_running` is `True`. This makes hot-reload safe: settings UI calls `App._on_config_changed`, which calls `self._hotkey.stop()` then constructs a new listener and `start()`s it.

### D7. `_dirty` flag for change tracking, not dict comparison

`SettingsWindow` tracks whether the user has changed anything since the last Apply via a boolean `_dirty`. Set to `True` by every input's `valueChanged` signal, set to `False` on Apply and Cancel. Simpler than comparing two deep-copied dicts and avoids the `QKeySequence == dict[str]` mismatch that bit us in the spec review.

### D8. `_load_values_into_ui` blocks signals during population

Filling combo boxes and radio groups from disk emits `currentIndexChanged` and friends, which would mark the form dirty during load. Wrap the load in `blockSignals(True)` for all input widgets, then unblock.

### D9. Settings X hides, doesn't close

`closeEvent` ignores the event and calls `hide()`. The app keeps running. Only the tray "Quit" action or the overlay context-menu "Quit" exits the process.

### D10. Overlay anchored to bottom-right of primary screen, no drag

`QGuiApplication.primaryScreen().availableGeometry()` minus margins. v1.1 may add drag with `mouseMoveEvent` and a `mouseGrabbed` flag.

### D11. Diagnostics section exposes paths and version

The "Diagnostics" section shows config path, model path, and app version as read-only `QLabel`s. Click-to-copy in v1.1. This is a deliberate nod to "developer-first" surface: paths and versions should always be one click away.

## Risks / Trade-offs

- **Pulse animation CPU**: `QPropertyAnimation` on `windowOpacity` is light. Tested ~0% CPU on i5-12500H. If it ever shows up in profiles, fall back to a `QTimer` that calls `setWindowOpacity` directly.
- **Multi-monitor**: only primary screen. v1.1 will add a screen picker.
- **DPI 4K**: 48px logical → 96px effective on 200% scale. Looks right because Qt scales the painter. No special handling needed.
- **Fullscreen apps**: `WindowStaysOnTopHint` keeps the overlay above normal fullscreen, but some games use exclusive fullscreen that ignores it. Acceptable v1 limitation.
- **Hotkey conflict on hot-reload**: the guard in `start()` makes this safe. The new listener only takes effect after the old one is unregistered. Tests cover the cycle.

## Migration Plan

N/A — additive change. Existing config files load unchanged; new fields get defaults on first read.

## Open Questions

- Should the overlay be position-configurable in v1? Decided: no, hard-coded bottom-right with 16px margin. v1.1.
- Should "Apply" be replaced by auto-save on change? Decided: no, explicit Apply matches the design language (each form field is a discrete verb). Auto-save hides the feedback loop.

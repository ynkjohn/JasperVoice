
from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen

import av
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QInputDialog

from jaspervoice.assets import icon_path
from jaspervoice.config import DEFAULT_CONFIG, get_models_dir
from jaspervoice.overlay import RecordingOverlay
from jaspervoice.theme import apply_theme
from jaspervoice.transcription import Transcriber
from jaspervoice.ui import SettingsWindow

out = Path(__file__).resolve().parents[1] / "public" / "showcase"
app = QApplication([])
app.setWindowIcon(QIcon(icon_path()))
apply_theme(app)

# The fixture is synthetic speech. Run it through the real local speech model.
resampler = av.AudioResampler(format="fltp", layout="mono", rate=16000)
with av.open(str(out / "dictation.wav")) as source:
    speech = np.concatenate([
        chunk.to_ndarray()[0] for frame in source.decode(audio=0) for chunk in resampler.resample(frame)
    ])
transcriber = Transcriber(model_size="tiny", device="cpu", language="en", download_root=get_models_dir())
result = transcriber.transcribe(speech)
assert result.text.strip()
(out / "transcript.json").write_text(json.dumps({"text": result.text}, ensure_ascii=False) + "\n", encoding="utf-8")

overlay = RecordingOverlay()
for state in ("recording", "processing", "send"):
    overlay.set_state(state)
    overlay.levels_updated.emit([0.2, 0.48, 0.75, 0.59, 0.26, 0.49, 0.28])
    QTest.qWait(245)
    assert overlay.grab().save(str(out / f"{state}.png"))
overlay.close()

cfg = deepcopy(DEFAULT_CONFIG)
cfg["language"] = "en"
window = SettingsWindow(cfg)
window.resize(1100, 690)
window.mic_source.start = lambda *_: None
window.show()
app.processEvents()
window.show_page("polish")
page = window.page("polish")
page.enabled.setChecked(True)
page.mode_seg.set_current_key("clean")
page.custom_prompt.setPlainText("Fix capitalization and punctuation. Keep the original language.")
# Optional real endpoint for capturing the Preview result without any account secret.
endpoint = os.environ.get("JASPER_SHOWCASE_ENDPOINT", "")
if endpoint:
    assert urlsplit(endpoint).hostname in ("localhost", "127.0.0.1", "::1")
    model = json.load(urlopen(endpoint.rstrip("/") + "/models", timeout=5))["data"][0]["id"]
    page.base_url.setText(endpoint)
    page.api_key_env.clear()
    page.fast_model.setEditText(model)
    page.smart_model.setEditText(model)
    dialog = QInputDialog.getMultiLineText
    try:
        QInputDialog.getMultiLineText = lambda *_: ("hi team the draft is ready for review", True)
        page.preview_btn.click()
        for _ in range(150):
            if page._thread is None:
                break
            QTest.qWait(200)
        assert "draft" in page.preview_status.text().lower(), page.preview_status.text()
    finally:
        QInputDialog.getMultiLineText = dialog

scroll = window._stack.currentWidget()
scroll.ensureWidgetVisible(page.preview_status, 8, 24)
app.processEvents()
assert page.preview_status.parentWidget().grab().save(str(out / "polish.png"))
window.shutdown_workers()
window.close()
print(result.text, flush=True)

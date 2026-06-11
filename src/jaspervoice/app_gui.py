"""Windowed (no-console) entry point for the packaged JasperVoice app.

When PyInstaller builds with ``console=False`` there is no attached console and
``sys.stdout`` / ``sys.stderr`` may be ``None``. The default
``logging.basicConfig`` (used by ``app.main``) writes to ``stderr`` and would
raise on the first log call. This entry point instead routes logging to a
rotating file under the per-user app dir, so the GUI build is fully silent and
still produces diagnosable logs.

The console build keeps using ``jaspervoice.app:main`` (logs to stderr).
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler


def _setup_file_logging() -> None:
    from jaspervoice.config import get_app_dir

    log_path = get_app_dir() / "jaspervoice.log"
    handler = RotatingFileHandler(
        log_path, maxBytes=512 * 1024, backupCount=2, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)


def main() -> int:
    _setup_file_logging()
    log = logging.getLogger(__name__)
    try:
        from jaspervoice.app import App

        app = App()
        return app.run()
    except Exception:
        log.exception("Fatal error during startup")
        return 1


if __name__ == "__main__":
    sys.exit(main())

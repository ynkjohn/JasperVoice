"""JasperVoice — local push-to-talk voice dictation for Windows.

``__version__`` is the single source of truth for the app version. It is read
by:
  - ``pyproject.toml`` (``project.dynamic = ["version"]``) at packaging time,
  - the Windows version resource baked into ``JasperVoice.exe`` (build script),
  - the Inno Setup installer (``installer/JasperVoice.iss`` reads it),
  - the in-app updater, which compares it against the latest GitHub Release tag.

Bump this one line to release a new version; everything downstream follows.
"""

__version__ = "1.0.0"

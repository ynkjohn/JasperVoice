# Security review

On November 27, 2026, this review covered the Windows **JasperVoice v1.2.0** release and its source at [`296a332`](https://github.com/ynkjohn/JasperVoice/commit/296a33225c1889a1f9579696798f0e351e86795a). It combined local regression tests, source review, dependency scanning, and verification of the published installer.

## What was checked

| Area | Result |
| --- | --- |
| Update and local installer verification | Tests rejected missing or mismatched SHA-256 values and covered download cancellation and fallback when the GitHub API is unavailable. The local v1.2.0 installer matched both the release manifest and GitHub's reported asset digest. |
| AI Polish and credentials | Tests covered rejected credentials, malformed completions, original-text fallback, and keeping the API key out of diagnostics. A local Qwen endpoint also processed the synthetic text used in the demo. |
| Dictation output and commands | Tests covered clipboard-free typing, recovery after a failed insertion, and the checks for configured whole-phrase shortcuts and executable launches. |
| Dependency review | `pip-audit` checked the installed Python environment. The reported finding affected the pinned test runner. After updating it to pytest 9.0.3, the same scan reported no known advisories for the scanned environment. `npm audit` also flagged packages in the video build toolchain. After updating Remotion and ESLint, the marketing audit reported no known advisories. The video toolchain is separate from the Windows installer. |

The Windows test run covered 161 targeted tests. The checks did not include fuzzing native libraries, bypassing Windows permissions, or attacking third-party services.

## What the checks mean for users

- **Installer authenticity.** The v1.2.0 setup is unsigned. A matching SHA-256 checks the downloaded bytes against the release manifest. Installers and manifests both come from the release you trust. [Release and checksum](https://github.com/ynkjohn/JasperVoice/releases/tag/v1.2.0)
- **Where dictation goes.** Standard dictation uses the window in focus after processing. Keep the intended text field focused until insertion completes.
- **Where transcript text goes.** JasperVoice keeps Whisper audio processing and recent transcript history on the PC. Optional AI Polish sends text to the configured endpoint. Use HTTPS when that endpoint is remote.

For a suspected vulnerability, contact [the maintainer](https://github.com/ynkjohn) privately with the app version and affected feature. Remove transcripts, credentials, and other private data from anything you share.

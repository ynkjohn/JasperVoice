# JasperVoice

**Voice dictation for Windows.** Hold `Ctrl + Shift + Space`, speak, and release. JasperVoice transcribes with Whisper on your PC and inserts the text into the focused app.

**[Download for Windows x64](https://github.com/ynkjohn/JasperVoice/releases/latest)** · [Setup guide](#get-started) · [Security review](docs/security-review.md)

## See it in action

[Watch the 19-second demo](docs/media/JasperVoice-1.2-demo.mp4?raw=true)

[Download the demo (MP4)](docs/media/JasperVoice-1.2-demo.mp4?raw=true) · [View the app screenshot](docs/media/JasperVoice-1.2-overview.png)

The demo shows dictation, the live microphone meter, and a Clean preview from the current Windows app. The spoken sample also appears on screen.

## Get started

1. Download and run `JasperVoice-Setup-<version>.exe` from [GitHub Releases](https://github.com/ynkjohn/JasperVoice/releases/latest). The installer runs per user.
2. Open JasperVoice and select **Test dictation** to check your microphone and verify that transcription works. On first use, the app downloads the selected Whisper model. The default `small` model is about 460 MB.
3. Focus a text field, hold **Ctrl + Shift + Space**, speak, then release. The shortcut and **Push to talk** / **Toggle** modes are configurable under **General**.

The main window opens on launch. Closing it keeps the hotkey available in the Windows tray. Use `--background` to start in the tray.

## What you can do

| Feature | Where to find it |
| --- | --- |
| Check input level and peaks, choose a mic, and try the dictation flow | **Overview** and **Audio & Mic** |
| Choose a Whisper model, prefer CUDA when available, or run on CPU | **Model & Engine** |
| Paste with Ctrl+V or type without using the clipboard | **General → Text insertion** |
| Search recent dictation, copy a result, or export history | **History** |
| Correct frequent misrecognitions or expand a term after transcription | **Dictionary** |
| Map an entire spoken phrase to a hotkey or a configured Windows executable | **Voice commands** |
| Clean up dictation, set a prompt for each style, and preview the result | **AI Polish** |

See [Dictation settings](docs/dictation-settings.md) for examples and the behavior of Type mode.

## AI Polish

AI Polish is optional. Transcription runs on your PC. If you enable AI Polish, JasperVoice sends the transcript text to the OpenAI-compatible endpoint you configure. Local servers such as Ollama or LM Studio can keep that processing on the same PC.

In **AI Polish**, add your endpoint, choose a model and style, then select **Preview Polish** to test with sample text. For providers that need a key, enter the **name** of its environment variable. Use HTTPS for remote providers.

## Privacy and updates

- Whisper processes audio on your PC. JasperVoice saves recent transcript text in the local history. Settings, history, and downloaded models live under `%APPDATA%\JasperVoice\`.
- JasperVoice connects to download Whisper models and check for releases. Turn off startup update checks in **Updates**. A remote AI Polish endpoint receives transcript text when you use that feature.
- The updater verifies the installer against the release’s SHA-256 manifest and asks before installing. The v1.2.0 installer has no Authenticode signature. See the [security review](docs/security-review.md) for the controls tested, the limits of checksum verification, and how to report a concern.

## Develop on Windows

Requires Python 3.11 or newer.

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e .
.venv\Scripts\python.exe -m jaspervoice
```

For tests, packaging, and the installer build, see [Development and releases](docs/development.md). The demo has [its own render instructions](marketing/README.md).

## License

[MIT](LICENSE)

# Dictation settings

## Type without touching the clipboard

Under **Settings → General → Text insertion**, use **Type** to send your
dictation as Unicode keystrokes. **Paste** remains the default for existing
settings. In Type mode, a line break sends Enter, which can submit a message
in some apps. If Windows rejects direct typing, you can recover the text
from **History**.

## Run actions with voice commands

Under **Settings → Voice commands**, add the phrases and actions you want,
turn on **Enable voice commands**, and choose **Apply**. These examples show three common actions.

| Spoken phrase | Action | Target |
| --- | --- | --- |
| Undo | Keyboard shortcut | `ctrl+z` |
| Show desktop | Keyboard shortcut | `windows+d` |
| Open Notepad | Run executable | `C:\Windows\System32\notepad.exe` |

A command runs only when the whole dictation matches the saved phrase,
ignoring case, final punctuation, and extra spaces. Keyboard shortcuts are
skipped if the foreground window changes while the dictation is processed.
Executables take a full `.exe` path and optional Windows command-line arguments.
The **Test dictation** button previews text without executing commands.

## Keep the original language in AI Polish

**Deutsch** is available as a spoken language in Settings and the tray, and
**Auto-detect** also works. The default AI Polish prompts ask the model to
preserve the original language and include the language code Whisper reported.
The result still depends on the model's ability to follow instructions.

Under **Settings → AI Polish → Output style**, select a style and edit its
**System prompt** to override the built-in prompt for that style. Use
**Restore default** to clear the override, then choose **Apply**.

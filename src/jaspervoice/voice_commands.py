"""Run user-defined Windows actions for whole-utterance voice commands."""

from __future__ import annotations

import subprocess
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import PureWindowsPath

import keyboard


def normalize_phrase(text: str) -> str:
    text = unicodedata.normalize("NFC", text).casefold()
    return " ".join(text.split()).rstrip(" .!?…")


@dataclass(frozen=True)
class VoiceCommand:
    phrase: str
    action: str
    target: str
    arguments: str = ""

    def as_config(self) -> dict[str, str]:
        return asdict(self)

    def validate(self) -> None:
        if not normalize_phrase(self.phrase):
            raise ValueError("Enter the exact phrase you want to say.")
        if not self.target or any(ord(char) < 32 for char in self.target + self.arguments):
            raise ValueError("Enter a valid shortcut or executable.")
        if self.action == "shortcut":
            try:
                steps = keyboard.parse_hotkey(self.target)
            except ValueError as exc:
                raise ValueError("Enter a keyboard shortcut such as ctrl+z or windows+d.") from exc
            if len(steps) != 1:
                raise ValueError("Enter a single keyboard shortcut.")
        elif self.action == "launch":
            path = PureWindowsPath(self.target)
            if not path.is_absolute() or path.suffix.lower() != ".exe":
                raise ValueError("Choose an executable (.exe) using its full path.")
        else:
            raise ValueError("Unknown voice command action.")

    def execute(self, original_window: int | None, current_window: int | None) -> None:
        self.validate()
        if self.action == "shortcut":
            if original_window is None or current_window != original_window:
                raise ValueError("The active window changed while transcribing.")
            keyboard.send(self.target)
        else:
            command_line = subprocess.list2cmdline([self.target])
            if self.arguments:
                command_line += " " + self.arguments
            subprocess.Popen(command_line, executable=self.target)


def parse_voice_commands(value: object) -> list[VoiceCommand]:
    commands: dict[str, VoiceCommand] = {}
    if not isinstance(value, list):
        return []
    for item in value:
        if not isinstance(item, dict):
            continue
        phrase, action, target, arguments = (
            item.get(key, "") for key in ("phrase", "action", "target", "arguments")
        )
        if not all(isinstance(field, str) for field in (phrase, action, target, arguments)):
            continue
        command = VoiceCommand(phrase.strip(), action, target.strip(), arguments.strip())
        key = normalize_phrase(command.phrase)
        if key and command.target and action in ("shortcut", "launch"):
            commands.setdefault(key, command)
    return list(commands.values())


def configured_voice_commands(cfg: dict) -> dict[str, VoiceCommand]:
    if cfg.get("voice_commands_enabled") is not True:
        return {}
    return {
        normalize_phrase(command.phrase): command
        for command in parse_voice_commands(cfg.get("voice_commands"))
    }

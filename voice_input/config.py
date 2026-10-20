"""Чтение и сохранение пользовательских настроек."""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from .paths import data_dir

log = logging.getLogger(__name__)

DEFAULT_HOTKEY = "ctrl+alt+space"


@dataclass
class AppConfig:
    device_key: str = ""
    hotkey: str = DEFAULT_HOTKEY
    auto_insert: bool = False
    auto_punctuation: bool = True
    voice_commands: bool = True
    auto_learn: bool = True
    start_with_windows: bool = False
    model_dir: str = ""
    max_duration: int = 300


def _coerce_bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "да"}
    if isinstance(value, (int, float)):
        return bool(value)
    return default


class ConfigStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (data_dir() / "config.json")

    def load(self) -> AppConfig:
        if not self.path.is_file():
            return AppConfig()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("config root is not an object")
            defaults = AppConfig()
            values: dict[str, object] = {}
            for item in fields(AppConfig):
                if item.name in raw:
                    values[item.name] = raw[item.name]
            config = AppConfig(
                device_key=str(values.get("device_key", defaults.device_key) or ""),
                hotkey=str(values.get("hotkey", defaults.hotkey) or DEFAULT_HOTKEY),
                auto_insert=_coerce_bool(
                    values.get("auto_insert", defaults.auto_insert), defaults.auto_insert
                ),
                auto_punctuation=_coerce_bool(
                    values.get("auto_punctuation", defaults.auto_punctuation),
                    defaults.auto_punctuation,
                ),
                voice_commands=_coerce_bool(
                    values.get("voice_commands", defaults.voice_commands),
                    defaults.voice_commands,
                ),
                auto_learn=_coerce_bool(
                    values.get("auto_learn", defaults.auto_learn),
                    defaults.auto_learn,
                ),
                start_with_windows=_coerce_bool(
                    values.get("start_with_windows", defaults.start_with_windows),
                    defaults.start_with_windows,
                ),
                model_dir=str(values.get("model_dir", defaults.model_dir) or ""),
                max_duration=int(values.get("max_duration", defaults.max_duration) or 300),
            )
            config.max_duration = max(10, min(3600, config.max_duration))
            return config
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            log.warning("Не удалось прочитать настройки: %s", exc)
            try:
                broken = self.path.with_name(
                    f"{self.path.stem}.broken-{int(time.time())}{self.path.suffix}"
                )
                os.replace(self.path, broken)
            except OSError:
                pass
            return AppConfig()

    def save(self, config: AppConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        try:
            tmp.write_text(
                json.dumps(asdict(config), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(tmp, self.path)
        except OSError as exc:
            log.error("Не удалось сохранить настройки: %s", exc)
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass

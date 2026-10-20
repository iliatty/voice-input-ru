"""Автозапуск при входе в Windows."""
from __future__ import annotations

import logging
import sys
import winreg
from pathlib import Path

from .paths import app_dir, is_frozen

log = logging.getLogger(__name__)

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "VoiceInputRU"


def startup_command() -> str:
    if is_frozen():
        return f'"{Path(sys.executable).resolve()}" --minimized'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    launcher = app_dir() / "run.pyw"
    return f'"{pythonw}" "{launcher}" --minimized'


def is_startup_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, VALUE_NAME)
            return bool(value)
    except OSError:
        return False


def set_startup_enabled(enabled: bool) -> None:
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        if enabled:
            winreg.SetValueEx(
                key,
                VALUE_NAME,
                0,
                winreg.REG_SZ,
                startup_command(),
            )
            log.info("Автозапуск включён: %s", startup_command())
        else:
            try:
                winreg.DeleteValue(key, VALUE_NAME)
                log.info("Автозапуск выключен")
            except FileNotFoundError:
                pass

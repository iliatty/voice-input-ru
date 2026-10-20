"""Глобальные горячие клавиши и их запись."""
from __future__ import annotations

import logging
import time
from typing import Callable

import keyboard

log = logging.getLogger(__name__)

MODIFIERS = ("ctrl", "alt", "shift", "windows")
_ALIASES = {
    "control": "ctrl",
    "ctl": "ctrl",
    "win": "windows",
    "meta": "windows",
    "cmd": "windows",
    "esc": "escape",
    "return": "enter",
    "spacebar": "space",
    "del": "delete",
    "ins": "insert",
    "pgup": "page up",
    "pgdn": "page down",
    "arrowup": "up",
    "arrowdown": "down",
    "arrowleft": "left",
    "arrowright": "right",
}
_DISPLAY = {
    "ctrl": "Ctrl",
    "alt": "Alt",
    "shift": "Shift",
    "windows": "Win",
    "space": "Space",
    "enter": "Enter",
    "escape": "Esc",
    "tab": "Tab",
    "backspace": "Backspace",
    "delete": "Delete",
    "insert": "Insert",
    "home": "Home",
    "end": "End",
    "page up": "Page Up",
    "page down": "Page Down",
    "up": "↑",
    "down": "↓",
    "left": "←",
    "right": "→",
    "print screen": "Print Screen",
}


def normalize_hotkey(combo: str) -> str:
    parts: list[str] = []
    for raw in (combo or "").lower().split("+"):
        part = raw.strip()
        if not part:
            continue
        part = _ALIASES.get(part, part)
        if part not in parts:
            parts.append(part)
    modifiers = [part for part in MODIFIERS if part in parts]
    keys = [part for part in parts if part not in MODIFIERS]
    return "+".join(modifiers + keys)


def format_hotkey(combo: str) -> str:
    normalized = normalize_hotkey(combo)
    if not normalized:
        return "Не задана"
    result: list[str] = []
    for part in normalized.split("+"):
        if part in _DISPLAY:
            result.append(_DISPLAY[part])
        elif len(part) == 1:
            result.append(part.upper())
        else:
            result.append(part.capitalize())
    return " + ".join(result)


def validate_hotkey(combo: str) -> tuple[bool, str]:
    normalized = normalize_hotkey(combo)
    if not normalized:
        return False, "Комбинация не задана."
    parts = normalized.split("+")
    modifiers = [part for part in parts if part in MODIFIERS]
    keys = [part for part in parts if part not in MODIFIERS]
    if not modifiers:
        return False, "Добавьте модификатор: Ctrl, Alt, Shift или Win."
    if len(keys) != 1:
        return False, "В комбинации должна быть одна основная клавиша."
    key = keys[0]
    if key in {"ctrl", "alt", "shift", "windows"}:
        return False, "Нужна основная клавиша, например Space или V."
    try:
        keyboard.key_to_scan_codes(key)
    except Exception:
        return False, f"Неизвестная клавиша: {key}"
    return True, ""


class GlobalHotkey:
    def __init__(self, callback: Callable[[], None]) -> None:
        self._callback = callback
        self._handle = None
        self.combo = ""
        self._last_trigger = 0.0

    def _pressed(self) -> None:
        now = time.monotonic()
        # Защита от автоповтора, если пользователь задержал клавишу.
        if now - self._last_trigger < 1.0:
            return
        self._last_trigger = now
        try:
            self._callback()
        except Exception:
            log.exception("Ошибка обработчика горячей клавиши")

    def register(self, combo: str) -> None:
        normalized = normalize_hotkey(combo)
        valid, message = validate_hotkey(normalized)
        if not valid:
            raise ValueError(message)
        self.unregister()
        handle = keyboard.add_hotkey(
            normalized,
            self._pressed,
            suppress=True,
            trigger_on_release=False,
        )
        self._handle = handle
        self.combo = normalized
        log.info("Горячая клавиша зарегистрирована: %s", normalized)

    def unregister(self) -> None:
        if self._handle is not None:
            try:
                keyboard.remove_hotkey(self._handle)
            except Exception:
                log.debug("Не удалось снять горячую клавишу", exc_info=True)
            self._handle = None
            self.combo = ""

    def shutdown(self) -> None:
        self.unregister()
        try:
            keyboard.unhook_all_hotkeys()
        except Exception:
            pass


def normalize_key_name(name: str | None) -> str:
    """Имя клавиши из события keyboard -> каноническое имя."""
    value = (name or "").strip().lower()
    for prefix in ("left ", "right "):
        if value.startswith(prefix):
            value = value[len(prefix) :]
    aliases = {
        "control": "ctrl",
        "win": "windows",
        "meta": "windows",
        "esc": "escape",
        "return": "enter",
        "spacebar": "space",
    }
    return aliases.get(value, value)


def read_hotkey() -> str | None:
    """Блокирующее чтение комбинации. None — пользователь нажал Esc.

    Оставлено для диагностики; интерфейс использует отменяемый hook.
    """
    time.sleep(0.15)
    try:
        combo = keyboard.read_hotkey(suppress=True)
    except Exception:
        log.exception("Не удалось прочитать горячую клавишу")
        return None
    normalized = normalize_hotkey(combo)
    if normalized in {"escape", "esc"}:
        return None
    return normalized

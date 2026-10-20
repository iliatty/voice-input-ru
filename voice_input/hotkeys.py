"""Глобальные горячие клавиши Windows без низкоуровневого перехвата клавиатуры."""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import logging
import threading
import time
from typing import Callable

import keyboard

log = logging.getLogger(__name__)

MODIFIERS = ("ctrl", "alt", "shift", "windows")
_MODIFIER_MASK = {
    "alt": 0x0001,
    "ctrl": 0x0002,
    "shift": 0x0004,
    "windows": 0x0008,
}
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
_HOTKEY_ID = 0x5652

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

_VK = {
    "space": 0x20,
    "enter": 0x0D,
    "escape": 0x1B,
    "tab": 0x09,
    "backspace": 0x08,
    "delete": 0x2E,
    "insert": 0x2D,
    "home": 0x24,
    "end": 0x23,
    "page up": 0x21,
    "page down": 0x22,
    "up": 0x26,
    "down": 0x28,
    "left": 0x25,
    "right": 0x27,
    "print screen": 0x2C,
    "pause": 0x13,
    "caps lock": 0x14,
    "num lock": 0x90,
    "scroll lock": 0x91,
    "plus": 0xBB,
    "minus": 0xBD,
    "comma": 0xBC,
    "period": 0xBE,
    "slash": 0xBF,
    "backslash": 0xDC,
    "semicolon": 0xBA,
    "apostrophe": 0xDE,
    "bracketleft": 0xDB,
    "bracketright": 0xDD,
    "grave": 0xC0,
}

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_user32.RegisterHotKey.argtypes = (wt.HWND, ctypes.c_int, wt.UINT, wt.UINT)
_user32.RegisterHotKey.restype = wt.BOOL
_user32.UnregisterHotKey.argtypes = (wt.HWND, ctypes.c_int)
_user32.UnregisterHotKey.restype = wt.BOOL
_user32.GetMessageW.argtypes = (
    ctypes.POINTER(wt.MSG),
    wt.HWND,
    wt.UINT,
    wt.UINT,
)
_user32.GetMessageW.restype = ctypes.c_int
_user32.PostThreadMessageW.argtypes = (wt.DWORD, wt.UINT, wt.WPARAM, wt.LPARAM)
_user32.PostThreadMessageW.restype = wt.BOOL
_user32.VkKeyScanW.argtypes = (wt.WCHAR,)
_user32.VkKeyScanW.restype = ctypes.c_short


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


def _key_to_vk(key: str) -> int | None:
    if key in _VK:
        return _VK[key]
    if len(key) == 1:
        code = _user32.VkKeyScanW(key)
        if code != -1:
            return code & 0xFF
    if len(key) >= 2 and key[0] == "f" and key[1:].isdigit():
        number = int(key[1:])
        if 1 <= number <= 24:
            return 0x6F + number
    return None


def _parse_hotkey(combo: str) -> tuple[int, int]:
    normalized = normalize_hotkey(combo)
    parts = normalized.split("+")
    modifiers = [part for part in parts if part in MODIFIERS]
    keys = [part for part in parts if part not in MODIFIERS]
    if not modifiers:
        raise ValueError("Добавьте модификатор: Ctrl, Alt, Shift или Win.")
    if len(keys) != 1:
        raise ValueError("В комбинации должна быть одна основная клавиша.")
    vk = _key_to_vk(keys[0])
    if vk is None:
        raise ValueError(f"Неизвестная клавиша: {keys[0]}")
    mask = 0
    for modifier in modifiers:
        mask |= _MODIFIER_MASK[modifier]
    return mask, vk


def validate_hotkey(combo: str) -> tuple[bool, str]:
    try:
        _parse_hotkey(combo)
    except ValueError as exc:
        return False, str(exc)
    return True, ""


class GlobalHotkey:
    """Регистрирует системную горячую клавишу через RegisterHotKey.

    В отличие от keyboard-hook, Windows не пропускает каждое нажатие через
    Python и не задерживает ввод в других приложениях.
    """

    def __init__(self, callback: Callable[[], None]) -> None:
        self._callback = callback
        self._thread: threading.Thread | None = None
        self._thread_id = 0
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._error = ""
        self.combo = ""
        self._last_trigger = 0.0

    def _pressed(self) -> None:
        now = time.monotonic()
        if now - self._last_trigger < 0.6:
            return
        self._last_trigger = now
        try:
            self._callback()
        except Exception:
            log.exception("Ошибка обработчика горячей клавиши")

    def register(self, combo: str) -> None:
        normalized = normalize_hotkey(combo)
        modifiers, vk = _parse_hotkey(normalized)
        self.unregister()
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._error = ""
        self._thread = threading.Thread(
            target=self._listen,
            args=(modifiers, vk),
            name="global-hotkey",
            daemon=True,
        )
        self._thread.start()
        if not self._ready.wait(2.0):
            self.unregister()
            raise RuntimeError("Не удалось запустить обработчик горячей клавиши.")
        if self._error:
            self.unregister()
            raise RuntimeError(self._error)
        self.combo = normalized
        log.info("Горячая клавиша зарегистрирована: %s", normalized)

    def _listen(self, modifiers: int, vk: int) -> None:
        if not _user32.RegisterHotKey(
            None,
            _HOTKEY_ID,
            modifiers | MOD_NOREPEAT,
            vk,
        ):
            error = ctypes.get_last_error()
            self._error = (
                "Комбинация занята другой программой "
                f"(код {error}). Назначьте другую."
            )
            self._ready.set()
            return

        self._thread_id = int(_kernel32.GetCurrentThreadId())
        self._ready.set()
        message = wt.MSG()
        try:
            while not self._stop.is_set():
                result = _user32.GetMessageW(ctypes.byref(message), None, 0, 0)
                if result == -1:
                    self._error = "Ошибка очереди сообщений Windows."
                    break
                if result == 0:
                    break
                if message.message == WM_HOTKEY and message.wParam == _HOTKEY_ID:
                    self._pressed()
        finally:
            _user32.UnregisterHotKey(None, _HOTKEY_ID)
            self._thread_id = 0

    def unregister(self) -> None:
        thread = self._thread
        if thread is None:
            self.combo = ""
            return
        self._stop.set()
        if self._thread_id:
            _user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        thread.join(timeout=1.5)
        self._thread = None
        self.combo = ""
        log.info("Горячая клавиша снята")

    def shutdown(self) -> None:
        self.unregister()


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
    """Блокирующее чтение комбинации для диагностики."""
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

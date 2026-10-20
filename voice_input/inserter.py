"""Вставка текста в окно, которое было активно до записи."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import keyboard
import pyperclip

from . import win_api

log = logging.getLogger(__name__)


@dataclass
class InsertResult:
    ok: bool
    copied: bool
    reason: str = ""


class TextInserter:
    def __init__(self) -> None:
        self.target_hwnd = 0
        self.target_title = ""

    def remember_foreground(self) -> None:
        hwnd = win_api.get_foreground_window()
        if not win_api.is_window(hwnd):
            return
        if win_api.is_own_window(hwnd):
            return
        self.target_hwnd = hwnd
        self.target_title = win_api.get_window_title(hwnd)

    def set_target(self, hwnd: int) -> None:
        self.target_hwnd = hwnd
        self.target_title = win_api.get_window_title(hwnd)

    def clear(self) -> None:
        self.target_hwnd = 0
        self.target_title = ""

    def insert(self, text: str) -> InsertResult:
        text = (text or "").strip()
        if not text:
            return InsertResult(False, False, "Пустой текст.")
        try:
            pyperclip.copy(text)
        except Exception as exc:
            log.exception("Не удалось скопировать текст")
            return InsertResult(False, False, f"Не удалось скопировать текст: {exc}")
        # Даём буферу обмена примениться.
        time.sleep(0.06)

        hwnd = self.target_hwnd
        if not win_api.is_window(hwnd):
            return InsertResult(
                False,
                True,
                "Окно для вставки закрыто. Текст скопирован — нажмите Ctrl+V вручную.",
            )
        if win_api.is_own_window(hwnd):
            return InsertResult(
                False,
                True,
                "Текст скопирован. Перейдите в нужное окно и нажмите Ctrl+V.",
            )
        if not win_api.focus_window(hwnd):
            return InsertResult(
                False,
                True,
                "Не удалось вернуть фокус в окно. Текст скопирован — нажмите Ctrl+V.",
            )
        time.sleep(0.08)
        try:
            keyboard.send("ctrl+v")
        except Exception as exc:
            log.exception("Не удалось отправить Ctrl+V")
            return InsertResult(
                False,
                True,
                f"Не удалось отправить Ctrl+V: {exc}\nТекст остался в буфере обмена.",
            )
        log.info("Текст вставлен в «%s» (%s символов)", self.target_title, len(text))
        return InsertResult(True, True)

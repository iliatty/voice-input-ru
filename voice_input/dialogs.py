"""Диалог записи новой горячей клавиши."""
from __future__ import annotations

import logging
import queue
import tkinter as tk
from tkinter import ttk

import keyboard

from . import win_api
from .config import DEFAULT_HOTKEY
from .hotkeys import (
    MODIFIERS,
    format_hotkey,
    normalize_hotkey,
    normalize_key_name,
    validate_hotkey,
)
from .theme import (
    BG,
    BORDER,
    FONT,
    FONT_SEMIBOLD,
    MUTED,
    RED,
    SURFACE,
    SURFACE_2,
    TEXT,
    apply_theme,
)

log = logging.getLogger(__name__)


class HotkeyDialog:
    def __init__(self, parent: tk.Tk, current: str = DEFAULT_HOTKEY) -> None:
        self.parent = parent
        self.current = normalize_hotkey(current or DEFAULT_HOTKEY)
        self.result: str | None = None
        self._events: queue.Queue[tuple[str, str]] = queue.Queue()
        self._closed = False
        self._poll_job: str | None = None
        self._hook = None
        self._pressed: set[str] = set()
        self._captured = False

        self.top = tk.Toplevel(parent)
        self.top.title("Горячая клавиша")
        self.top.configure(bg=BG)
        self.top.resizable(False, False)
        self.top.transient(parent)
        self.top.protocol("WM_DELETE_WINDOW", self._cancel)
        self.top.bind("<Escape>", lambda _event: self._cancel())
        self._build()
        self._center(470, 292)
        apply_theme(self.top)
        win_api.set_dark_title_bar(self.top)
        self.top.bind(
            "<FocusIn>",
            lambda _event: win_api.set_dark_title_bar(self.top),
            add="+",
        )
        for delay in (250, 700, 1500):
            self.top.after(delay, lambda: win_api.set_dark_title_bar(self.top))
        self.top.grab_set()
        self.top.after(120, self._start_capture)
        self._poll_job = self.top.after(60, self._poll)

    def _build(self) -> None:
        outer = tk.Frame(
            self.top,
            bg=SURFACE,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        outer.pack(fill="both", expand=True, padx=18, pady=18)

        tk.Label(
            outer,
            text="Нажмите новую комбинацию",
            bg=SURFACE,
            fg=TEXT,
            font=(FONT_SEMIBOLD, 15),
        ).pack(anchor="w", padx=20, pady=(18, 4))
        tk.Label(
            outer,
            text="Например: Ctrl + Alt + Space или Ctrl + Shift + F9",
            bg=SURFACE,
            fg=MUTED,
            font=(FONT, 9),
        ).pack(anchor="w", padx=20)

        self.combo_frame = tk.Frame(
            outer,
            bg=SURFACE_2,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        self.combo_frame.pack(fill="x", padx=20, pady=(18, 6))
        self.combo_label = tk.Label(
            self.combo_frame,
            text=format_hotkey(self.current),
            bg=SURFACE_2,
            fg=TEXT,
            font=(FONT_SEMIBOLD, 15),
            pady=15,
        )
        self.combo_label.pack(fill="x")

        self.hint_label = tk.Label(
            outer,
            text="Ожидаю нажатия…  Esc — отмена",
            bg=SURFACE,
            fg=MUTED,
            font=(FONT, 9),
            anchor="w",
        )
        self.hint_label.pack(fill="x", padx=20, pady=(0, 10))

        buttons = tk.Frame(outer, bg=SURFACE)
        buttons.pack(fill="x", padx=20, pady=(2, 16))
        ttk.Button(
            buttons,
            text="Сбросить",
            style="Link.TButton",
            command=self._reset,
        ).pack(side="left")
        ttk.Button(
            buttons,
            text="Отмена",
            style="Ghost.TButton",
            command=self._cancel,
        ).pack(side="right")

    def _center(self, width: int, height: int) -> None:
        self.parent.update_idletasks()
        x = self.parent.winfo_rootx() + max(0, (self.parent.winfo_width() - width) // 2)
        y = self.parent.winfo_rooty() + max(0, (self.parent.winfo_height() - height) // 2)
        self.top.geometry(f"{width}x{height}+{x}+{y}")

    def _start_capture(self) -> None:
        if self._closed or self._hook is not None:
            return
        self.combo_label.configure(text="Ожидание…", fg=MUTED)
        self._pressed.clear()
        try:
            self._hook = keyboard.hook(self._on_key_event, suppress=True)
        except Exception as exc:
            self.hint_label.configure(text=f"Не удалось перехватить клавиатуру: {exc}")
            log.exception("Не удалось установить hook для горячей клавиши")

    def _on_key_event(self, event) -> None:
        if self._closed or self._captured:
            return
        name = normalize_key_name(getattr(event, "name", None))
        if not name:
            return
        if event.event_type == keyboard.KEY_UP:
            self._pressed.discard(name)
            return
        if event.event_type != keyboard.KEY_DOWN:
            return

        if name == "escape":
            self._events.put(("cancel", ""))
            return
        if name in MODIFIERS:
            self._pressed.add(name)
            return
        modifiers = [item for item in MODIFIERS if item in self._pressed]
        if not modifiers:
            self._events.put(
                ("invalid", "Добавьте модификатор: Ctrl, Alt, Shift или Win.")
            )
            return
        combo = normalize_hotkey("+".join(modifiers + [name]))
        valid, message = validate_hotkey(combo)
        if valid:
            self._captured = True
            self._events.put(("ok", combo))
        else:
            self._events.put(("invalid", message))

    def _poll(self) -> None:
        if self._closed:
            return
        try:
            kind, value = self._events.get_nowait()
        except queue.Empty:
            self._poll_job = self.top.after(60, self._poll)
            return
        if kind == "ok":
            self.result = value
            self._close()
        elif kind == "cancel":
            self._cancel()
        elif kind == "invalid":
            self.combo_label.configure(text="Не подходит", fg=RED)
            self.hint_label.configure(text=f"{value} Попробуйте ещё раз. Esc — отмена.")
            self._poll_job = self.top.after(60, self._poll)
        else:
            self._poll_job = self.top.after(60, self._poll)

    def _reset(self) -> None:
        self.result = DEFAULT_HOTKEY
        self._close()

    def _cancel(self) -> None:
        self.result = None
        self._close()

    def _close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._hook is not None:
            try:
                keyboard.unhook(self._hook)
            except Exception:
                pass
            self._hook = None
        if self._poll_job is not None:
            try:
                self.top.after_cancel(self._poll_job)
            except tk.TclError:
                pass
            self._poll_job = None
        try:
            self.top.grab_release()
        except tk.TclError:
            pass
        try:
            self.top.destroy()
        except tk.TclError:
            pass

    def show(self) -> str | None:
        self.parent.wait_window(self.top)
        return self.result

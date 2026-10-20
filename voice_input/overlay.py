"""Компактное плавающее окно записи и подтверждения текста."""
from __future__ import annotations

import math
import time
import tkinter as tk
from tkinter import ttk
from typing import Callable

from . import win_api
from .theme import (
    ACCENT,
    AMBER,
    BORDER,
    FONT,
    FONT_SEMIBOLD,
    GREEN,
    MUTED,
    RED,
    SURFACE,
    SURFACE_2,
    TEXT,
    apply_text_style,
)

WIDTH = 524
HEIGHT_RECORDING = 238
HEIGHT_PREVIEW = 356


class OverlayCallbacks:
    def __init__(
        self,
        on_stop: Callable[[], None],
        on_cancel: Callable[[], None],
        on_insert: Callable[[], None],
        on_copy: Callable[[], None],
        on_retry: Callable[[], None],
    ) -> None:
        self.on_stop = on_stop
        self.on_cancel = on_cancel
        self.on_insert = on_insert
        self.on_copy = on_copy
        self.on_retry = on_retry


class RecordingOverlay:
    def __init__(self, root: tk.Tk, callbacks: OverlayCallbacks) -> None:
        self.root = root
        self.callbacks = callbacks
        self.state = "hidden"
        self._levels: list[float] = [0.0] * 26
        self._last_level = 0.0
        self._phase = 0
        self._anim_job: str | None = None
        self._started_at = 0.0
        self._timer_text = "00:00"

        self.top = tk.Toplevel(root)
        self.top.withdraw()
        self.top.overrideredirect(True)
        self.top.configure(bg=BORDER)
        self.top.attributes("-topmost", True)
        try:
            self.top.attributes("-alpha", 0.985)
        except tk.TclError:
            pass
        self.top.bind("<Escape>", self._on_escape)

        outer = tk.Frame(self.top, bg=BORDER)
        outer.pack(fill="both", expand=True)
        self.inner = tk.Frame(outer, bg=SURFACE)
        self.inner.pack(fill="both", expand=True, padx=1, pady=1)

        self._build_header()
        self._build_body()
        self._build_footer()

    # ---------- построение ----------

    def _build_header(self) -> None:
        header = tk.Frame(self.inner, bg=SURFACE)
        header.pack(fill="x", padx=18, pady=(14, 0))
        left = tk.Frame(header, bg=SURFACE)
        left.pack(side="left", fill="x", expand=True)

        top_row = tk.Frame(left, bg=SURFACE)
        top_row.pack(fill="x")
        self.dot = tk.Canvas(
            top_row,
            width=14,
            height=14,
            bg=SURFACE,
            highlightthickness=0,
            bd=0,
        )
        self.dot.pack(side="left", pady=(2, 0))
        self._dot_id = self.dot.create_oval(3, 3, 11, 11, fill=RED, outline="")

        self.title_label = tk.Label(
            top_row,
            text="Идёт запись",
            bg=SURFACE,
            fg=TEXT,
            font=(FONT_SEMIBOLD, 12),
        )
        self.title_label.pack(side="left", padx=(8, 0))

        self.timer_label = tk.Label(
            top_row,
            text="00:00",
            bg=SURFACE,
            fg=MUTED,
            font=(FONT_SEMIBOLD, 11),
        )
        self.timer_label.pack(side="right", padx=(8, 6))

        close = tk.Label(
            top_row,
            text="×",
            bg=SURFACE,
            fg=MUTED,
            font=(FONT, 17),
            cursor="hand2",
            padx=4,
        )
        close.pack(side="right")
        close.bind("<Button-1>", lambda _event: self._close_clicked())
        close.bind("<Enter>", lambda _event: close.configure(fg=TEXT))
        close.bind("<Leave>", lambda _event: close.configure(fg=MUTED))

        self.target_label = tk.Label(
            left,
            text="",
            bg=SURFACE,
            fg=MUTED,
            font=(FONT, 9),
            anchor="w",
        )
        self.target_label.pack(fill="x", padx=(22, 0), pady=(2, 0))

        self.separator = tk.Frame(self.inner, bg=BORDER, height=1)
        self.separator.pack(fill="x", padx=18, pady=(12, 0))

    def _build_body(self) -> None:
        self.body = tk.Frame(self.inner, bg=SURFACE)
        self.body.pack(fill="both", expand=True, padx=18, pady=(12, 0))

        self.partial_label = tk.Label(
            self.body,
            text="Говорите…",
            bg=SURFACE,
            fg=MUTED,
            font=(FONT, 12),
            wraplength=WIDTH - 70,
            justify="left",
            anchor="nw",
            height=3,
        )
        self.partial_label.pack(fill="x", anchor="w")

        self.text_edit = tk.Text(self.body, height=5, wrap="word")
        apply_text_style(self.text_edit)
        self.text_edit.bind("<Control-Return>", self._insert_event)
        self.text_edit.bind("<Escape>", self._on_escape)

        self.hint_label = tk.Label(
            self.body,
            text="",
            bg=SURFACE,
            fg=MUTED,
            font=(FONT, 9),
            anchor="w",
            justify="left",
            wraplength=WIDTH - 70,
        )

    def _build_footer(self) -> None:
        footer = tk.Frame(self.inner, bg=SURFACE)
        footer.pack(fill="x", padx=18, pady=(10, 14))
        footer.grid_columnconfigure(0, weight=1)
        self.footer = footer

        left = tk.Frame(footer, bg=SURFACE)
        left.grid(row=0, column=0, sticky="w")
        self.footer_left = left
        self.level_canvas = tk.Canvas(
            left,
            width=150,
            height=24,
            bg=SURFACE,
            highlightthickness=0,
            bd=0,
        )
        self.level_canvas.pack(anchor="w")
        self.shortcut_label = tk.Label(
            left,
            text="",
            bg=SURFACE,
            fg=MUTED,
            font=(FONT, 8),
            anchor="w",
        )
        self.shortcut_label.pack(anchor="w", pady=(4, 0))

        buttons = tk.Frame(footer, bg=SURFACE)
        buttons.grid(row=0, column=1, sticky="e")
        self.btn_tertiary = ttk.Button(
            buttons, text="Закрыть", style="Ghost.TButton", takefocus=False
        )
        self.btn_secondary = ttk.Button(
            buttons, text="Отмена", style="Ghost.TButton", takefocus=False
        )
        self.btn_primary = ttk.Button(
            buttons, text="Остановить", style="Record.TButton", takefocus=False
        )

    # ---------- показ состояний ----------

    def _place(self, height: int, activate: bool) -> None:
        self.top.update_idletasks()
        x, y = win_api.overlay_position(WIDTH, height)
        self.top.geometry(f"{WIDTH}x{height}+{x}+{y}")
        self.top.deiconify()
        self.top.lift()
        self.top.update_idletasks()
        hwnd = win_api.top_level_hwnd(self.top)
        if activate:
            self.top.focus_force()
            win_api.set_topmost(hwnd)
        else:
            win_api.show_no_activate(hwnd)

    def _set_dot(self, color: str) -> None:
        self.dot.itemconfigure(self._dot_id, fill=color)

    def _clear_buttons(self) -> None:
        for button in (self.btn_primary, self.btn_secondary, self.btn_tertiary):
            button.pack_forget()

    def _show_buttons(
        self,
        primary: tuple[str, str, Callable[[], None]] | None = None,
        secondary: tuple[str, str, Callable[[], None]] | None = None,
        tertiary: tuple[str, str, Callable[[], None]] | None = None,
    ) -> None:
        self._clear_buttons()
        if tertiary:
            text, style, command = tertiary
            self.btn_tertiary.configure(text=text, style=style, command=command)
            self.btn_tertiary.pack(side="left", padx=(0, 8))
        if secondary:
            text, style, command = secondary
            self.btn_secondary.configure(text=text, style=style, command=command)
            self.btn_secondary.pack(side="left", padx=(0, 8))
        if primary:
            text, style, command = primary
            self.btn_primary.configure(text=text, style=style, command=command)
            self.btn_primary.pack(side="left")

    def show_recording(self, target_title: str = "") -> None:
        self.state = "recording"
        self._levels = [0.0] * 26
        self._last_level = 0.0
        self._started_at = time.monotonic()
        self._timer_text = "00:00"
        self.timer_label.configure(text="00:00")
        self.title_label.configure(text="Идёт запись")
        self._set_dot(RED)
        self.target_label.configure(
            text=f"Куда: {self._shorten(target_title)}" if target_title else "Куда: активное окно"
        )
        self.partial_label.configure(text="Говорите…", fg=MUTED, height=3)
        self.partial_label.pack(fill="x", anchor="w")
        self.text_edit.pack_forget()
        self.hint_label.pack_forget()
        self.shortcut_label.configure(text="Enter — стоп  ·  Esc — отмена")
        self.level_canvas.pack(anchor="w", before=self.shortcut_label)
        self.timer_label.pack(side="right", padx=(8, 6))
        self._show_buttons(
            primary=("■  Остановить", "Record.TButton", self.callbacks.on_stop),
            secondary=("Отмена", "Ghost.TButton", self.callbacks.on_cancel),
        )
        self._place(HEIGHT_RECORDING, activate=False)
        self._start_animation()

    def show_processing(self) -> None:
        self.state = "processing"
        self.title_label.configure(text="Распознаю…")
        self._set_dot(AMBER)
        self.partial_label.configure(text="Обрабатываю запись…", fg=MUTED)
        self.shortcut_label.configure(text="Это займёт меньше секунды")
        self.level_canvas.pack(anchor="w", before=self.shortcut_label)
        self._show_buttons()
        self._draw_levels(static=True)
        self._start_animation()

    def show_preview(self, text: str) -> None:
        self.state = "preview"
        self._stop_animation()
        self.title_label.configure(text="Готово")
        self._set_dot(GREEN)
        self.timer_label.pack_forget()
        self.level_canvas.pack_forget()
        self.partial_label.pack_forget()
        self.hint_label.pack_forget()
        self.text_edit.pack(fill="both", expand=True, pady=(0, 4))
        self.text_edit.delete("1.0", "end")
        self.text_edit.insert("1.0", text)
        self.text_edit.edit_reset()
        self.text_edit.mark_set("insert", "end-1c")
        self.text_edit.see("end")
        self.shortcut_label.configure(text="Ctrl+Enter — вставить · Esc")
        self._show_buttons(
            primary=("Вставить", "Primary.TButton", self.callbacks.on_insert),
            secondary=("Копировать", "Ghost.TButton", self.callbacks.on_copy),
            tertiary=("Закрыть", "Ghost.TButton", self.callbacks.on_cancel),
        )
        self._place(HEIGHT_PREVIEW, activate=True)
        self.text_edit.focus_set()

    def show_error(self, message: str, *, retry: bool = True) -> None:
        self.state = "error"
        self._stop_animation()
        self.title_label.configure(text="Не получилось")
        self._set_dot(RED)
        self.timer_label.pack_forget()
        self.level_canvas.pack_forget()
        self.text_edit.pack_forget()
        self.partial_label.pack(fill="x", anchor="w")
        display = (message or "").strip()
        if len(display) > 260:
            display = display[:259].rstrip() + "…"
        self.partial_label.configure(text=display, fg=TEXT, height=4)
        self.hint_label.configure(text="")
        self.hint_label.pack(fill="x", anchor="w", pady=(6, 0))
        self.shortcut_label.configure(text="Esc — закрыть")
        buttons = []
        if retry:
            buttons.append(("Повторить", "Primary.TButton", self.callbacks.on_retry))
        self._show_buttons(
            primary=buttons[0] if buttons else None,
            secondary=("Закрыть", "Ghost.TButton", self.callbacks.on_cancel),
        )
        self._place(HEIGHT_RECORDING, activate=True)

    def show_copied(self) -> None:
        self.btn_secondary.configure(text="Скопировано")
        self.shortcut_label.configure(text="Текст в буфере обмена — вставьте его через Ctrl+V")

    def set_partial(self, text: str) -> None:
        if self.state != "recording":
            return
        cleaned = " ".join((text or "").split())
        if cleaned:
            display = cleaned[0].upper() + cleaned[1:]
            if len(display) > 210:
                display = "…" + display[-209:]
            self.partial_label.configure(text=display, fg=TEXT)
        else:
            self.partial_label.configure(text="Говорите…", fg=MUTED)

    def set_level(self, level: float) -> None:
        self._last_level = max(0.0, min(1.0, level))

    def set_target(self, title: str) -> None:
        self.target_label.configure(
            text=f"Куда: {self._shorten(title)}" if title else "Куда: активное окно"
        )

    def get_text(self) -> str:
        if self.state != "preview":
            return ""
        return self.text_edit.get("1.0", "end-1c").strip()

    def hide(self) -> None:
        self.state = "hidden"
        self._stop_animation()
        self.top.withdraw()

    def destroy(self) -> None:
        self._stop_animation()
        try:
            self.top.destroy()
        except tk.TclError:
            pass

    # ---------- анимация ----------

    def _start_animation(self) -> None:
        self._stop_animation()
        self._phase = 0
        self._animate()

    def _stop_animation(self) -> None:
        if self._anim_job is not None:
            try:
                self.top.after_cancel(self._anim_job)
            except tk.TclError:
                pass
            self._anim_job = None

    def _animate(self) -> None:
        if self.state not in {"recording", "processing"}:
            self._anim_job = None
            return
        self._phase += 1
        if self.state == "recording":
            elapsed = int(time.monotonic() - self._started_at)
            timer = f"{elapsed // 60:02d}:{elapsed % 60:02d}"
            if timer != self._timer_text:
                self._timer_text = timer
                self.timer_label.configure(text=timer)
            pulse = 0.55 + 0.45 * (0.5 + 0.5 * math.sin(self._phase * 0.28))
            r = int(255)
            g = int(40 + 70 * pulse)
            b = int(55 + 70 * pulse)
            self._set_dot(f"#{r:02x}{g:02x}{b:02x}")
        self._levels = self._levels[1:] + [
            max(self._last_level, self._levels[-1] * 0.72)
        ]
        self._draw_levels()
        self._anim_job = self.top.after(55, self._animate)

    def _draw_levels(self, static: bool = False) -> None:
        canvas = self.level_canvas
        canvas.delete("all")
        bars = 26
        width = 4
        gap = 2
        total = bars * width + (bars - 1) * gap
        x0 = (150 - total) // 2
        mid = 12
        for index in range(bars):
            level = self._levels[index] if not static else 0.0
            variation = 0.6 + 0.4 * abs(math.sin(index * 1.37 + 0.8))
            height = int(2 + level * 19 * variation)
            x = x0 + index * (width + gap)
            color = ACCENT if level < 0.75 else RED
            canvas.create_rectangle(
                x,
                mid - height // 2,
                x + width,
                mid + height // 2 + 1,
                fill=color,
                outline="",
            )

    # ---------- события ----------

    def _on_escape(self, _event=None) -> str:
        if self.state in {"recording", "processing", "preview", "error"}:
            self.callbacks.on_cancel()
        return "break"

    def _insert_event(self, _event=None) -> str:
        if self.state == "preview":
            self.callbacks.on_insert()
        return "break"

    def _close_clicked(self) -> None:
        if self.state in {"recording", "processing", "preview", "error"}:
            self.callbacks.on_cancel()

    @staticmethod
    def _shorten(text: str, limit: int = 58) -> str:
        text = " ".join((text or "").split())
        if len(text) <= limit:
            return text
        return text[: limit - 1].rstrip() + "…"

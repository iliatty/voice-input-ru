"""Окно просмотра и очистки словаря самообучения."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable

from . import win_api
from .learning import LearningStore
from .theme import (
    BG,
    BORDER,
    FONT,
    FONT_SEMIBOLD,
    MUTED,
    SURFACE,
    TEXT,
    TEXT_SOFT,
    apply_theme,
)


class LearningDialog:
    def __init__(
        self,
        parent: tk.Tk,
        store: LearningStore,
        on_changed: Callable[[], None] | None = None,
    ) -> None:
        self.parent = parent
        self.store = store
        self.on_changed = on_changed
        self.top = tk.Toplevel(parent)
        self.top.title("Словарь самообучения")
        self.top.configure(bg=BG)
        self.top.resizable(False, False)
        self.top.transient(parent)
        self.top.protocol("WM_DELETE_WINDOW", self._close)
        self.top.bind("<Escape>", lambda _event: self._close())
        self._build()
        self._center(640, 540)
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
        self._refresh()

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
            text="Словарь самообучения",
            bg=SURFACE,
            fg=TEXT,
            font=(FONT_SEMIBOLD, 15),
        ).pack(anchor="w", padx=20, pady=(18, 3))
        self.hint = tk.Label(
            outer,
            text="Программа запоминает ваши исправления в окне предпросмотра.",
            bg=SURFACE,
            fg=MUTED,
            font=(FONT, 9),
            anchor="w",
        )
        self.hint.pack(fill="x", padx=20, pady=(0, 12))

        table_frame = tk.Frame(outer, bg=SURFACE)
        table_frame.pack(fill="both", expand=True, padx=20)

        columns = ("wrong", "correct", "count")
        self.tree = ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            selectmode="extended",
            height=8,
        )
        self.tree.heading("wrong", text="Распознано")
        self.tree.heading("correct", text="Исправлено")
        self.tree.heading("count", text="Раз")
        self.tree.column("wrong", width=245, anchor="w")
        self.tree.column("correct", width=245, anchor="w")
        self.tree.column("count", width=55, anchor="center", stretch=False)
        scrollbar = ttk.Scrollbar(
            table_frame,
            orient="vertical",
            command=self.tree.yview,
        )
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.empty_label = tk.Label(
            table_frame,
            text="Пока пусто. Исправьте слово в предпросмотре — и оно появится здесь.",
            bg=SURFACE,
            fg=MUTED,
            font=(FONT, 9),
            wraplength=520,
        )

        buttons = tk.Frame(outer, bg=SURFACE)
        buttons.pack(fill="x", padx=20, pady=(14, 16))
        ttk.Button(
            buttons,
            text="Удалить выбранное",
            style="Ghost.TButton",
            command=self._remove_selected,
        ).pack(side="left")
        ttk.Button(
            buttons,
            text="Очистить всё",
            style="Ghost.TButton",
            command=self._clear_all,
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            buttons,
            text="Закрыть",
            style="Primary.TButton",
            command=self._close,
        ).pack(side="right")

    def _refresh(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        for pair in self.store.pairs():
            self.tree.insert(
                "",
                "end",
                values=(pair.wrong, pair.correct, pair.count),
            )
        if self.store.count:
            self.empty_label.place_forget()
            self.hint.configure(
                text=f"Запомнено замен: {self.store.count}. "
                "Они применяются к новым расшифровкам."
            )
        else:
            self.empty_label.place(relx=0.5, rely=0.45, anchor="center")

    def _remove_selected(self) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        for item in selected:
            values = self.tree.item(item, "values")
            if len(values) >= 2:
                self.store.remove(str(values[0]), str(values[1]))
        self._refresh()
        if self.on_changed:
            self.on_changed()

    def _clear_all(self) -> None:
        if not self.store.count:
            return
        if not messagebox.askyesno(
            "Словарь самообучения",
            "Удалить все запомненные исправления?",
            parent=self.top,
        ):
            return
        self.store.clear()
        self._refresh()
        if self.on_changed:
            self.on_changed()

    def _center(self, width: int, height: int) -> None:
        self.parent.update_idletasks()
        x = self.parent.winfo_rootx() + max(0, (self.parent.winfo_width() - width) // 2)
        y = self.parent.winfo_rooty() + max(0, (self.parent.winfo_height() - height) // 2)
        self.top.geometry(f"{width}x{height}+{x}+{y}")

    def _close(self) -> None:
        try:
            self.top.grab_release()
        except tk.TclError:
            pass
        self.top.destroy()

    def show(self) -> None:
        self.parent.wait_window(self.top)

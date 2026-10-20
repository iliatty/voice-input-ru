"""Тёмная тема интерфейса."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

# Палитра
BG = "#0E1015"
SURFACE = "#161A22"
SURFACE_2 = "#1D222C"
SURFACE_3 = "#252B37"
BORDER = "#2C3341"
TEXT = "#F3F5F9"
TEXT_SOFT = "#D7DCE5"
MUTED = "#8D97A8"
ACCENT = "#5B8CFF"
ACCENT_HOVER = "#709BFF"
ACCENT_PRESSED = "#4A78E8"
RED = "#FF5566"
RED_HOVER = "#FF6D7B"
GREEN = "#3DDC97"
AMBER = "#FFC35B"

FONT = "Segoe UI"
FONT_SEMIBOLD = "Segoe UI Semibold"


def apply_theme(root: tk.Misc) -> ttk.Style:
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    root.option_add("*Font", (FONT, 10))
    root.configure(bg=BG)

    style.configure(".", background=BG, foreground=TEXT, font=(FONT, 10))
    style.configure("TFrame", background=BG)
    style.configure("Surface.TFrame", background=SURFACE)
    style.configure("Surface2.TFrame", background=SURFACE_2)
    style.configure("TLabel", background=BG, foreground=TEXT)
    style.configure("Surface.TLabel", background=SURFACE, foreground=TEXT)
    style.configure("SurfaceMuted.TLabel", background=SURFACE, foreground=MUTED)
    style.configure("Muted.TLabel", background=BG, foreground=MUTED)
    style.configure(
        "Title.TLabel",
        background=BG,
        foreground=TEXT,
        font=(FONT_SEMIBOLD, 23),
    )
    style.configure(
        "Subtitle.TLabel",
        background=BG,
        foreground=MUTED,
        font=(FONT, 10),
    )
    style.configure(
        "Section.TLabel",
        background=SURFACE,
        foreground=TEXT,
        font=(FONT_SEMIBOLD, 10),
    )
    style.configure(
        "Hint.TLabel",
        background=SURFACE,
        foreground=MUTED,
        font=(FONT, 9),
    )
    style.configure(
        "KeyCap.TLabel",
        background=SURFACE_2,
        foreground=TEXT,
        font=(FONT_SEMIBOLD, 11),
        padding=(14, 8),
    )

    style.configure(
        "TButton",
        background=SURFACE_2,
        foreground=TEXT,
        bordercolor=BORDER,
        lightcolor=SURFACE_2,
        darkcolor=SURFACE_2,
        focuscolor=SURFACE_2,
        padding=(14, 8),
        relief="flat",
    )
    style.map(
        "TButton",
        background=[("active", SURFACE_3), ("pressed", SURFACE_3), ("disabled", SURFACE)],
        foreground=[("disabled", "#5E6777")],
    )

    style.configure(
        "Primary.TButton",
        background=ACCENT,
        foreground="#FFFFFF",
        bordercolor=ACCENT,
        lightcolor=ACCENT,
        darkcolor=ACCENT,
        focuscolor=ACCENT,
        font=(FONT_SEMIBOLD, 10),
        padding=(18, 10),
    )
    style.map(
        "Primary.TButton",
        background=[
            ("active", ACCENT_HOVER),
            ("pressed", ACCENT_PRESSED),
            ("disabled", "#333C4D"),
        ],
        foreground=[("disabled", "#778196")],
        bordercolor=[("active", ACCENT_HOVER), ("disabled", "#333C4D")],
    )

    style.configure(
        "Record.TButton",
        background=RED,
        foreground="#FFFFFF",
        bordercolor=RED,
        lightcolor=RED,
        darkcolor=RED,
        focuscolor=RED,
        font=(FONT_SEMIBOLD, 11),
        padding=(22, 13),
    )
    style.map(
        "Record.TButton",
        background=[("active", RED_HOVER), ("pressed", "#E64758"), ("disabled", "#333C4D")],
        foreground=[("disabled", "#778196")],
    )

    style.configure(
        "Ghost.TButton",
        background=SURFACE_2,
        foreground=TEXT_SOFT,
        bordercolor=BORDER,
        lightcolor=SURFACE_2,
        darkcolor=SURFACE_2,
        padding=(14, 9),
    )
    style.map(
        "Ghost.TButton",
        background=[("active", SURFACE_3), ("pressed", SURFACE_3)],
        foreground=[("disabled", "#5E6777")],
    )

    style.configure(
        "Link.TButton",
        background=SURFACE,
        foreground=ACCENT,
        bordercolor=SURFACE,
        lightcolor=SURFACE,
        darkcolor=SURFACE,
        padding=(8, 6),
        font=(FONT, 9),
    )
    style.map(
        "Link.TButton",
        background=[("active", SURFACE_2), ("pressed", SURFACE_2)],
        foreground=[("active", ACCENT_HOVER)],
    )

    style.configure(
        "TCombobox",
        fieldbackground=SURFACE_2,
        background=SURFACE_2,
        foreground=TEXT,
        arrowcolor=TEXT_SOFT,
        bordercolor=BORDER,
        lightcolor=BORDER,
        darkcolor=BORDER,
        padding=(10, 7),
        relief="flat",
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", SURFACE_2), ("disabled", SURFACE)],
        foreground=[("readonly", TEXT), ("disabled", MUTED)],
        bordercolor=[("focus", ACCENT), ("hover", "#3C4557")],
        selectbackground=[("readonly", SURFACE_2)],
        selectforeground=[("readonly", TEXT)],
    )
    root.option_add("*TCombobox*Listbox.background", SURFACE_2)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
    root.option_add("*TCombobox*Listbox.selectForeground", "#FFFFFF")
    root.option_add("*TCombobox*Listbox.borderWidth", 0)

    style.configure(
        "Card.TCheckbutton",
        background=SURFACE,
        foreground=TEXT_SOFT,
        focuscolor=SURFACE,
        font=(FONT, 10),
        indicatorbackground=SURFACE_2,
        indicatorforeground=MUTED,
        indicatorcolor=SURFACE_2,
        indicatormargin=(0, 0, 7, 0),
    )
    style.map(
        "Card.TCheckbutton",
        background=[("active", SURFACE)],
        foreground=[("active", TEXT)],
        indicatorbackground=[
            ("selected", ACCENT),
            ("pressed", ACCENT_PRESSED),
            ("active", SURFACE_3),
        ],
        indicatorcolor=[
            ("selected", ACCENT),
            ("pressed", ACCENT_PRESSED),
            ("active", SURFACE_3),
        ],
        indicatorforeground=[("selected", "#FFFFFF"), ("!selected", MUTED)],
    )

    style.configure(
        "Treeview",
        background=SURFACE_2,
        fieldbackground=SURFACE_2,
        foreground=TEXT,
        bordercolor=BORDER,
        borderwidth=0,
        rowheight=26,
        font=(FONT, 9),
    )
    style.configure(
        "Treeview.Heading",
        background=SURFACE_3,
        foreground=TEXT_SOFT,
        font=(FONT_SEMIBOLD, 9),
        relief="flat",
        padding=(6, 5),
    )
    style.map(
        "Treeview",
        background=[("selected", ACCENT)],
        foreground=[("selected", "#FFFFFF")],
    )
    style.map(
        "Treeview.Heading",
        background=[("active", SURFACE_3)],
    )

    style.configure(
        "Accent.Horizontal.TProgressbar",
        troughcolor=SURFACE_2,
        background=ACCENT,
        bordercolor=SURFACE_2,
        lightcolor=ACCENT,
        darkcolor=ACCENT,
        thickness=5,
    )

    style.configure(
        "Vertical.TScrollbar",
        background=SURFACE_2,
        troughcolor=SURFACE,
        bordercolor=SURFACE,
        arrowcolor=MUTED,
        lightcolor=SURFACE_2,
        darkcolor=SURFACE_2,
    )
    return style


def apply_text_style(widget: tk.Text) -> None:
    widget.configure(
        bg=SURFACE_2,
        fg=TEXT,
        insertbackground=TEXT,
        selectbackground=ACCENT,
        selectforeground="#FFFFFF",
        relief="flat",
        borderwidth=0,
        highlightthickness=1,
        highlightbackground=BORDER,
        highlightcolor=ACCENT,
        font=(FONT, 10),
        padx=10,
        pady=8,
        spacing1=1,
        spacing3=2,
        wrap="word",
    )

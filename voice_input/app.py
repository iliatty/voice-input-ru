"""Главное окно приложения «Голосовой ввод»."""
from __future__ import annotations

import logging
import queue
import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import pyperclip

from . import startup, win_api
from .audio import Recorder, default_input_device, list_input_devices
from .config import DEFAULT_HOTKEY, AppConfig, ConfigStore
from .dialogs import HotkeyDialog
from .hotkeys import GlobalHotkey, format_hotkey
from .inserter import TextInserter
from .learning import LearningStore
from .learning_dialog import LearningDialog
from .model_manager import download_model_async, load_model_async
from .overlay import OverlayCallbacks, RecordingOverlay
from .paths import (
    APP_TITLE,
    MODEL_FOLDER_NAME,
    VERSION,
    find_model_dir,
    model_is_valid,
    resource_path,
)
from .text_utils import format_transcript
from .tray import TrayController
from .theme import (
    ACCENT,
    ACCENT_HOVER,
    AMBER,
    BG,
    BORDER,
    FONT,
    FONT_SEMIBOLD,
    GREEN,
    MUTED,
    RED,
    SURFACE,
    SURFACE_2,
    SURFACE_3,
    TEXT,
    TEXT_SOFT,
    apply_theme,
)

log = logging.getLogger(__name__)


class StatusBadge(tk.Frame):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(
            parent,
            bg=SURFACE_2,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        self._dot = tk.Canvas(
            self,
            width=10,
            height=10,
            bg=SURFACE_2,
            highlightthickness=0,
            bd=0,
        )
        self._dot.pack(side="left", padx=(10, 6), pady=7)
        self._oval = self._dot.create_oval(1, 1, 9, 9, fill=AMBER, outline="")
        self._label = tk.Label(
            self,
            text="Загрузка…",
            bg=SURFACE_2,
            fg=TEXT_SOFT,
            font=(FONT, 9),
        )
        self._label.pack(side="left", padx=(0, 12), pady=6)

    def set(self, text: str, color: str = GREEN) -> None:
        self._dot.itemconfigure(self._oval, fill=color)
        self._label.configure(text=text)


class VoiceInputApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self._closing = False
        self.config_store = ConfigStore()
        self.config: AppConfig = self.config_store.load()
        self.model = None
        self.model_path: Path | None = None
        self.recorder: Recorder | None = None
        self.state = "idle"
        self.session_id = 0
        self.last_text = ""
        self._recognized_text = ""
        self._tray_hint_shown = False
        self.learning = LearningStore()
        initial_foreground = win_api.get_foreground_window()
        if (
            initial_foreground
            and win_api.is_window(initial_foreground)
            and not win_api.is_own_window(initial_foreground)
        ):
            self.last_external_hwnd = initial_foreground
            self.last_external_title = win_api.get_window_title(initial_foreground)
        else:
            self.last_external_hwnd = 0
            self.last_external_title = ""
        self._record_started_at = 0.0
        self._duration_job: str | None = None
        self._watchdog_job: str | None = None
        self.events: queue.Queue[tuple[str, tuple]] = queue.Queue()
        self.devices = []

        self.inserter = TextInserter()
        self.overlay = RecordingOverlay(
            root,
            OverlayCallbacks(
                on_stop=self._stop_recording,
                on_cancel=self._cancel_session,
                on_insert=self._insert_current,
                on_copy=self._copy_current,
                on_retry=self._retry_recording,
            ),
        )
        self.hotkey = GlobalHotkey(lambda: self._post("hotkey"))
        self.tray = TrayController()

        self._configure_window()
        self._build_ui()
        self._load_settings_into_ui()
        self._register_hotkey_initial()
        self._refresh_devices(initial=True)
        self.tray.start(
            on_show=lambda: self._post("tray_show"),
            on_record=lambda: self._post("tray_record"),
            on_exit=lambda: self._post("tray_exit"),
        )

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(50, self._poll_events)
        self.root.after(200, self._load_model)
        self.root.after(350, self._track_foreground)
        if "--minimized" in sys.argv:
            if self.tray.available:
                self.root.withdraw()
            else:
                self.root.after(400, self.root.iconify)

    # ------------------------------------------------------------------ окно

    def _configure_window(self) -> None:
        self.root.title(f"{APP_TITLE} — русская речь в текст")
        self.root.configure(bg=BG)
        apply_theme(self.root)
        self.root.minsize(760, 645)
        width, height = 780, 650
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        win_api.set_app_user_model_id()
        icon_path = resource_path("assets/icon.png")
        if icon_path.is_file():
            try:
                self._icon = tk.PhotoImage(file=str(icon_path))
                self.root.iconphoto(True, self._icon)
            except tk.TclError:
                log.debug("Не удалось загрузить иконку", exc_info=True)
        self.root.update_idletasks()
        win_api.set_dark_title_bar(self.root)
        self.root.bind(
            "<FocusIn>",
            lambda _event: win_api.set_dark_title_bar(self.root),
            add="+",
        )
        for delay in (300, 800, 1600, 3200, 6000):
            self.root.after(delay, lambda: win_api.set_dark_title_bar(self.root))

    def _build_ui(self) -> None:
        container = tk.Frame(self.root, bg=BG)
        container.pack(fill="both", expand=True, padx=26, pady=(20, 14))
        self.container = container

        self._build_header(container)
        self._build_settings(container)
        self._build_action(container)
        self._build_last_text(container)
        self._build_footer(container)

    def _build_header(self, parent: tk.Frame) -> None:
        header = tk.Frame(parent, bg=BG)
        header.pack(fill="x")
        left = tk.Frame(header, bg=BG)
        left.pack(side="left", fill="x", expand=True)
        tk.Label(
            left,
            text="Голосовой ввод",
            bg=BG,
            fg=TEXT,
            font=(FONT_SEMIBOLD, 23),
            anchor="w",
        ).pack(anchor="w")
        tk.Label(
            left,
            text="Русская речь — сразу в текст, в любом приложении",
            bg=BG,
            fg=MUTED,
            font=(FONT, 9),
            anchor="w",
        ).pack(anchor="w", pady=(1, 0))
        self.status_badge = StatusBadge(header)
        self.status_badge.pack(side="right", anchor="n", pady=(4, 0))

    def _build_settings(self, parent: tk.Frame) -> None:
        card = tk.Frame(
            parent,
            bg=SURFACE,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        card.pack(fill="x", pady=(16, 0))

        head = tk.Frame(card, bg=SURFACE)
        head.pack(fill="x", padx=18, pady=(12, 10))
        tk.Label(
            head,
            text="Настройки",
            bg=SURFACE,
            fg=TEXT,
            font=(FONT_SEMIBOLD, 11),
        ).pack(side="left")
        self.model_hint = tk.Label(
            head,
            text="Whisper Small · офлайн",
            bg=SURFACE,
            fg=MUTED,
            font=(FONT, 8),
        )
        self.model_hint.pack(side="right")

        tk.Frame(card, bg=BORDER, height=1).pack(fill="x")

        content = tk.Frame(card, bg=SURFACE)
        content.pack(fill="x", padx=18, pady=13)
        content.grid_columnconfigure(1, weight=1)

        # Микрофон
        tk.Label(
            content,
            text="Микрофон",
            bg=SURFACE,
            fg=TEXT_SOFT,
            font=(FONT, 10),
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=(0, 14), pady=5)
        self.device_combo = ttk.Combobox(
            content,
            state="readonly",
            height=12,
            font=(FONT, 9),
        )
        self.device_combo.grid(row=0, column=1, sticky="ew", pady=5)
        self.device_combo.bind("<<ComboboxSelected>>", self._on_device_selected)
        self.refresh_button = ttk.Button(
            content,
            text="Обновить",
            style="Ghost.TButton",
            command=self._refresh_devices,
            takefocus=False,
        )
        self.refresh_button.grid(row=0, column=2, sticky="e", padx=(8, 0), pady=5)

        # Горячая клавиша
        tk.Label(
            content,
            text="Горячая клавиша",
            bg=SURFACE,
            fg=TEXT_SOFT,
            font=(FONT, 10),
            anchor="w",
        ).grid(row=1, column=0, sticky="w", padx=(0, 14), pady=5)
        self.key_frame = tk.Frame(
            content,
            bg=SURFACE_2,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        self.key_frame.grid(row=1, column=1, sticky="w", pady=5)
        self.key_label = tk.Label(
            self.key_frame,
            text="Ctrl + Alt + Space",
            bg=SURFACE_2,
            fg=TEXT,
            font=(FONT_SEMIBOLD, 10),
            padx=13,
            pady=7,
        )
        self.key_label.pack()
        self.change_hotkey_button = ttk.Button(
            content,
            text="Изменить",
            style="Ghost.TButton",
            command=self._change_hotkey,
            takefocus=False,
        )
        self.change_hotkey_button.grid(
            row=1, column=2, sticky="e", padx=(8, 0), pady=5
        )

        # Параметры
        self._check_off = None
        self._check_on = None
        try:
            self._check_off = tk.PhotoImage(
                file=str(resource_path("assets/check-off.png"))
            )
            self._check_on = tk.PhotoImage(
                file=str(resource_path("assets/check-on.png"))
            )
        except tk.TclError:
            log.debug("Не удалось загрузить иконки чекбоксов", exc_info=True)

        options = tk.Frame(content, bg=SURFACE)
        options.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(9, 0))
        options.grid_columnconfigure(0, weight=1)
        options.grid_columnconfigure(1, weight=1)

        self.auto_insert_var = tk.BooleanVar(value=self.config.auto_insert)
        self.auto_punct_var = tk.BooleanVar(value=self.config.auto_punctuation)
        self.voice_cmd_var = tk.BooleanVar(value=self.config.voice_commands)
        self.auto_learn_var = tk.BooleanVar(value=self.config.auto_learn)
        self.startup_var = tk.BooleanVar(value=False)

        self._checkbutton(
            options,
            "Вставлять сразу после распознавания",
            self.auto_insert_var,
            self._on_auto_insert,
        ).grid(row=0, column=0, sticky="w", pady=2)
        self._checkbutton(
            options,
            "Пунктуация и заглавные буквы",
            self.auto_punct_var,
            self._on_punctuation,
        ).grid(row=0, column=1, sticky="w", pady=2, padx=(10, 0))
        self._checkbutton(
            options,
            "Голосовые команды пунктуации",
            self.voice_cmd_var,
            self._on_voice_commands,
        ).grid(row=1, column=0, sticky="w", pady=2)
        self._checkbutton(
            options,
            "Запускать при входе в Windows",
            self.startup_var,
            self._on_startup_toggle,
        ).grid(row=1, column=1, sticky="w", pady=2, padx=(10, 0))
        self._checkbutton(
            options,
            "Учиться на моих исправлениях",
            self.auto_learn_var,
            self._on_auto_learn,
        ).grid(row=2, column=0, sticky="w", pady=2)
        self.learning_button = ttk.Button(
            options,
            text="Словарь",
            style="Link.TButton",
            command=self._open_learning_dialog,
            takefocus=False,
        )
        self.learning_button.grid(
            row=2, column=1, sticky="w", padx=(6, 0), pady=1
        )

        # Скачивание модели (показывается только если модели нет)
        self.model_bar = tk.Frame(
            content,
            bg=SURFACE_2,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        self.model_bar_label = tk.Label(
            self.model_bar,
            text="Модель распознавания не найдена",
            bg=SURFACE_2,
            fg=TEXT_SOFT,
            font=(FONT, 9),
            anchor="w",
        )
        self.model_bar_label.pack(side="left", padx=10, pady=8)
        self.download_button = ttk.Button(
            self.model_bar,
            text="Скачать 486 МБ",
            style="Link.TButton",
            command=self._download_model,
        )
        self.download_button.pack(side="right", padx=4)
        self.browse_model_button = ttk.Button(
            self.model_bar,
            text="Указать папку",
            style="Link.TButton",
            command=self._browse_model,
        )
        self.browse_model_button.pack(side="right", padx=2)
        self.model_progress = ttk.Progressbar(
            self.model_bar,
            mode="determinate",
            maximum=100,
            style="Accent.Horizontal.TProgressbar",
            length=90,
        )
        self._model_bar_visible = False

    def _checkbutton(
        self,
        parent: tk.Misc,
        text: str,
        variable: tk.BooleanVar,
        command,
    ) -> tk.Widget:
        if self._check_on is None or self._check_off is None:
            return ttk.Checkbutton(
                parent,
                text=text,
                variable=variable,
                command=command,
                style="Card.TCheckbutton",
                takefocus=False,
            )
        button = tk.Checkbutton(
            parent,
            text=text,
            variable=variable,
            command=command,
            image=self._check_off,
            selectimage=self._check_on,
            indicatoron=False,
            compound="left",
            bg=SURFACE,
            fg=TEXT_SOFT,
            activebackground=SURFACE,
            activeforeground=TEXT,
            selectcolor=SURFACE,
            bd=0,
            highlightthickness=0,
            font=(FONT, 10),
            anchor="w",
            cursor="hand2",
            padx=0,
            pady=2,
        )
        button.bind(
            "<Enter>", lambda _event: button.configure(fg=TEXT)
        )
        button.bind(
            "<Leave>", lambda _event: button.configure(fg=TEXT_SOFT)
        )
        return button

    def _build_action(self, parent: tk.Frame) -> None:
        self.record_button = tk.Button(
            parent,
            text="●   Начать запись",
            command=self.toggle_recording,
            bg=ACCENT,
            fg="#FFFFFF",
            activebackground=ACCENT_HOVER,
            activeforeground="#FFFFFF",
            disabledforeground="#778196",
            font=(FONT_SEMIBOLD, 12),
            bd=0,
            relief="flat",
            highlightthickness=0,
            cursor="hand2",
            pady=13,
        )
        self.record_button.pack(fill="x", pady=(14, 0))
        self.record_button.bind("<Enter>", lambda _e: self._record_hover(True))
        self.record_button.bind("<Leave>", lambda _e: self._record_hover(False))

        hint_row = tk.Frame(parent, bg=BG)
        hint_row.pack(fill="x", pady=(7, 0))
        self.hotkey_hint = tk.Label(
            hint_row,
            text="",
            bg=BG,
            fg=MUTED,
            font=(FONT, 8),
        )
        self.hotkey_hint.pack(side="left")
        tk.Label(
            hint_row,
            text="Повторное нажатие — остановить",
            bg=BG,
            fg=MUTED,
            font=(FONT, 8),
        ).pack(side="right")

    def _build_last_text(self, parent: tk.Frame) -> None:
        card = tk.Frame(
            parent,
            bg=SURFACE,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        card.pack(fill="x", pady=(13, 0))
        self.last_card = card
        head = tk.Frame(card, bg=SURFACE)
        head.pack(fill="x", padx=14, pady=(8, 2))
        tk.Label(
            head,
            text="Последняя расшифровка",
            bg=SURFACE,
            fg=TEXT_SOFT,
            font=(FONT_SEMIBOLD, 9),
        ).pack(side="left")
        self.copy_last_button = ttk.Button(
            head,
            text="Копировать",
            style="Link.TButton",
            command=self._copy_last_text,
            takefocus=False,
        )
        self.last_text_label = tk.Label(
            card,
            text="Здесь появится распознанный текст.",
            bg=SURFACE,
            fg=MUTED,
            font=(FONT, 9),
            anchor="nw",
            justify="left",
            wraplength=680,
            height=3,
        )
        self.last_text_label.pack(fill="x", padx=14, pady=(0, 8))

    def _build_footer(self, parent: tk.Frame) -> None:
        footer = tk.Frame(parent, bg=BG)
        footer.pack(fill="x", side="bottom", pady=(8, 0))
        self.footer_label = tk.Label(
            footer,
            text="Подготовка…",
            bg=BG,
            fg=MUTED,
            font=(FONT, 8),
            anchor="w",
        )
        self.footer_label.pack(side="left")
        tk.Label(
            footer,
            text=f"v{VERSION}",
            bg=BG,
            fg="#5E6777",
            font=(FONT, 8),
        ).pack(side="right")

    # ------------------------------------------------------------- настройки

    def _load_settings_into_ui(self) -> None:
        self.key_label.configure(text=format_hotkey(self.config.hotkey))
        self.auto_insert_var.set(self.config.auto_insert)
        self.auto_punct_var.set(self.config.auto_punctuation)
        self.voice_cmd_var.set(self.config.voice_commands)
        self.auto_learn_var.set(self.config.auto_learn)
        self._update_learning_button()
        try:
            enabled = startup.is_startup_enabled()
        except OSError:
            enabled = False
        self.config.start_with_windows = enabled
        self.startup_var.set(enabled)
        self._update_hotkey_hint()

    def _save_config(self) -> None:
        self.config_store.save(self.config)

    def _update_hotkey_hint(self) -> None:
        self.hotkey_hint.configure(
            text=f"{format_hotkey(self.config.hotkey)} — начать или остановить запись"
        )

    def _refresh_devices(self, initial: bool = False) -> None:
        self.devices = list_input_devices()
        current_key = self.config.device_key
        default = default_input_device()
        default_label = "Системный по умолчанию"
        if default is not None:
            default_label += f" — {default.name}"

        if not self.devices:
            self.device_combo.configure(values=["Микрофоны не найдены"])
            self.device_combo.current(0)
            self.device_combo.configure(state="disabled")
            self.refresh_button.configure(state="normal")
            self.footer_label.configure(
                text="Микрофон не найден. Подключите устройство ввода и нажмите «Обновить»."
            )
            return

        values = [default_label] + [device.label for device in self.devices]
        self.device_combo.configure(values=values, state="readonly")
        selected = 0
        if current_key:
            for index, device in enumerate(self.devices, start=1):
                if device.key == current_key:
                    selected = index
                    break
            else:
                self.footer_label.configure(
                    text="Сохранённый микрофон не найден — выбран системный по умолчанию."
                )
                self.config.device_key = ""
                self._save_config()
        self.device_combo.current(selected)
        if not initial:
            self.footer_label.configure(
                text=f"Найдено устройств ввода: {len(self.devices)}."
            )

    def _on_device_selected(self, _event=None) -> None:
        index = self.device_combo.current()
        if index <= 0:
            self.config.device_key = ""
        else:
            self.config.device_key = self.devices[index - 1].key
        self._save_config()
        name = "системный по умолчанию" if index <= 0 else self.devices[index - 1].name
        self.footer_label.configure(text=f"Микрофон: {name}.")
        if self.state == "recording" and self.recorder is not None:
            self.footer_label.configure(
                text="Устройство применится со следующей записи."
            )

    def _on_auto_insert(self) -> None:
        self.config.auto_insert = bool(self.auto_insert_var.get())
        self._save_config()

    def _on_punctuation(self) -> None:
        self.config.auto_punctuation = bool(self.auto_punct_var.get())
        self._save_config()

    def _on_voice_commands(self) -> None:
        self.config.voice_commands = bool(self.voice_cmd_var.get())
        self._save_config()

    def _on_auto_learn(self) -> None:
        self.config.auto_learn = bool(self.auto_learn_var.get())
        self._save_config()

    def _update_learning_button(self) -> None:
        if hasattr(self, "learning_button"):
            self.learning_button.configure(text=f"Словарь ({self.learning.count})")

    def _open_learning_dialog(self) -> None:
        LearningDialog(
            self.root,
            self.learning,
            on_changed=self._update_learning_button,
        ).show()

    def _on_startup_toggle(self) -> None:
        enabled = bool(self.startup_var.get())
        try:
            startup.set_startup_enabled(enabled)
        except OSError as exc:
            self.startup_var.set(not enabled)
            messagebox.showerror(
                "Автозапуск",
                f"Не удалось изменить автозапуск:\n{exc}",
                parent=self.root,
            )
            return
        self.config.start_with_windows = enabled
        self._save_config()
        self.footer_label.configure(
            text="Автозапуск включён." if enabled else "Автозапуск выключен."
        )

    # --------------------------------------------------------------- hotkey

    def _register_hotkey_initial(self) -> None:
        candidates: list[str] = []
        for combo in (self.config.hotkey, DEFAULT_HOTKEY, "ctrl+alt+f9", "ctrl+shift+f9"):
            if combo and combo not in candidates:
                candidates.append(combo)
        last_error: Exception | None = None
        for index, combo in enumerate(candidates):
            try:
                self.hotkey.register(combo)
            except Exception as exc:
                last_error = exc
                log.warning("Не удалось зарегистрировать %s: %s", combo, exc)
                continue
            if combo != self.config.hotkey:
                self.config.hotkey = combo
                self._save_config()
                self.footer_label.configure(
                    text=f"Комбинация была занята — назначена {format_hotkey(combo)}."
                )
            break
        else:
            log.error("Все горячие клавиши заняты: %s", last_error)
            self.status_badge.set("Горячая клавиша недоступна", RED)
            self.footer_label.configure(
                text="Все предложенные комбинации заняты. Запись доступна кнопкой."
            )
        if self.hotkey.combo:
            self.key_label.configure(text=format_hotkey(self.config.hotkey), fg=TEXT)
        else:
            self.key_label.configure(text="Недоступна", fg=RED)
        self._update_hotkey_hint()

    def _change_hotkey(self) -> None:
        old = self.hotkey.combo or self.config.hotkey
        self.hotkey.unregister()
        try:
            dialog = HotkeyDialog(self.root, old)
            combo = dialog.show()
        finally:
            if not self.hotkey.combo:
                try:
                    self.hotkey.register(old)
                except Exception:
                    log.exception("Не удалось вернуть старую горячую клавишу")

        if combo is None:
            self.key_label.configure(text=format_hotkey(old))
            return
        try:
            self.hotkey.register(combo)
        except Exception as exc:
            messagebox.showerror(
                "Горячая клавиша",
                f"Не удалось назначить {format_hotkey(combo)}:\n{exc}",
                parent=self.root,
            )
            try:
                self.hotkey.register(old)
            except Exception:
                log.exception("Не удалось вернуть старую горячую клавишу")
            return
        self.config.hotkey = combo
        self._save_config()
        self.key_label.configure(text=format_hotkey(combo), fg=TEXT)
        self._update_hotkey_hint()
        self.footer_label.configure(
            text=f"Горячая клавиша: {format_hotkey(combo)}."
        )

    # ----------------------------------------------------------------- model

    def _load_model(self) -> None:
        path = find_model_dir(self.config.model_dir)
        if path is None:
            self._show_model_missing()
            return
        self.model_path = path
        self.model_hint.configure(text="Whisper Small · офлайн")
        self.status_badge.set("Загрузка модели…", AMBER)
        self.footer_label.configure(text=f"Модель: {path}")
        self._set_record_mode("loading")
        load_model_async(
            path,
            lambda model: self._post("model_ready", model),
            lambda error: self._post("model_error", error),
        )

    def _show_model_missing(self) -> None:
        self.status_badge.set("Модель не найдена", RED)
        self.model_hint.configure(text="Модель не найдена", fg=RED)
        self.footer_label.configure(
            text="Скачайте модель один раз — дальше программа работает офлайн."
        )
        self._set_record_mode("disabled")
        if not self._model_bar_visible:
            self.model_bar.grid(
                row=4, column=0, columnspan=3, sticky="ew", pady=(10, 0)
            )
            self._model_bar_visible = True

    def _hide_model_bar(self) -> None:
        if self._model_bar_visible:
            self.model_bar.grid_remove()
            self._model_bar_visible = False
        self.model_hint.configure(text="Whisper Small · офлайн", fg=MUTED)

    def _on_model_ready(self, model) -> None:
        self.model = model
        self._hide_model_bar()
        self.status_badge.set("Готово к работе", GREEN)
        if self.hotkey.combo:
            self.footer_label.configure(
                text="Модель загружена. Нажмите горячую клавишу и говорите."
            )
        else:
            self.footer_label.configure(
                text="Модель загружена, но глобальная клавиша недоступна. "
                "Запись доступна кнопкой."
            )
        self._set_record_mode("start")

    def _on_model_error(self, error: str) -> None:
        self.status_badge.set("Ошибка модели", RED)
        self.footer_label.configure(text=f"Модель не загрузилась: {error}")
        self._show_model_missing()
        messagebox.showerror(
            "Модель распознавания",
            "Не удалось загрузить модель Whisper.\n\n"
            f"{error}\n\n"
            "Можно скачать модель заново или указать папку вручную.",
            parent=self.root,
        )

    def _download_model(self) -> None:
        self.download_button.configure(state="disabled")
        self.browse_model_button.configure(state="disabled")
        self.model_progress.pack(side="right", padx=(2, 10), before=self.browse_model_button)
        self.model_progress["value"] = 0
        self.model_bar_label.configure(text="Скачивание модели…")
        download_model_async(
            lambda percent, text: self._post("download_progress", percent, text),
            lambda path: self._post("download_ready", path),
            lambda error: self._post("download_error", error),
        )
        self.footer_label.configure(text="Скачивание модели Whisper (486 МБ)…")

    def _on_download_progress(self, percent: int, text: str) -> None:
        self.model_progress["value"] = max(0, min(100, percent))
        self.model_bar_label.configure(text=text)
        self.footer_label.configure(text=text)

    def _on_download_ready(self, path: Path) -> None:
        self.download_button.configure(state="normal")
        self.browse_model_button.configure(state="normal")
        self.model_progress.pack_forget()
        self.config.model_dir = str(path)
        self._save_config()
        self.footer_label.configure(text="Модель скачана. Загружаю…")
        self._load_model()

    def _on_download_error(self, error: str) -> None:
        self.download_button.configure(state="normal")
        self.browse_model_button.configure(state="normal")
        self.model_progress.pack_forget()
        self.model_bar_label.configure(text="Не удалось скачать модель")
        self.status_badge.set("Ошибка загрузки", RED)
        messagebox.showerror(
            "Скачивание модели",
            f"{error}\n\nМожно указать папку с уже скачанной моделью.",
            parent=self.root,
        )

    def _browse_model(self) -> None:
        selected = filedialog.askdirectory(
            parent=self.root,
            title=f"Выберите папку модели {MODEL_FOLDER_NAME}",
        )
        if not selected:
            return
        path = Path(selected)
        if not model_is_valid(path) and model_is_valid(path / MODEL_FOLDER_NAME):
            path = path / MODEL_FOLDER_NAME
        if not model_is_valid(path):
            messagebox.showerror(
                "Модель",
                "В выбранной папке нет модели Whisper.\n\n"
                "Выберите папку, внутри которой есть model.bin, config.json, "
                "tokenizer.json и vocabulary.txt.",
                parent=self.root,
            )
            return
        self.config.model_dir = str(path)
        self._save_config()
        self.model = None
        self._load_model()

    # --------------------------------------------------------------- запись

    def toggle_recording(self) -> None:
        if self.state == "recording":
            self._stop_recording()
        elif self.state == "preview":
            self._insert_current()
        elif self.state == "idle":
            self._start_recording()
        elif self.state == "error":
            self._cancel_session()

    def _start_recording(self, reuse_target: bool = False) -> None:
        if self.model is None:
            self.status_badge.set("Модель не готова", AMBER)
            self.footer_label.configure(text="Дождитесь загрузки модели.")
            return
        if self.state in {"recording", "processing"}:
            return
        if self.state == "preview":
            self._cancel_session(silent=True)

        self._pick_target(reuse_target=reuse_target)
        self.session_id += 1
        self._recognized_text = ""
        session = self.session_id
        self.state = "recording"
        self._record_started_at = time.monotonic()
        self.status_badge.set("Идёт запись", RED)
        self.footer_label.configure(
            text="Говорите. Повторное нажатие горячей клавиши остановит запись."
        )
        self._set_record_mode("stop")
        self.overlay.show_recording(self.inserter.target_title)

        self.recorder = Recorder(
            self.model,
            on_partial=lambda text: self._post("partial", session, text),
            on_final=lambda text: self._post("final", session, text),
            on_level=lambda level: self._post("level", session, level),
            on_error=lambda error: self._post("audio_error", session, error),
        )
        started = self.recorder.start(self.config.device_key)
        if not started:
            self._cancel_jobs()
            return
        self._duration_job = self.root.after(1000, self._check_duration)

    def _pick_target(self, reuse_target: bool = False) -> None:
        foreground = win_api.get_foreground_window()
        if foreground and not win_api.is_own_window(foreground) and win_api.is_window(foreground):
            self.inserter.set_target(foreground)
            return
        if reuse_target and win_api.is_window(self.inserter.target_hwnd):
            return
        if (
            self.last_external_hwnd
            and win_api.is_window(self.last_external_hwnd)
            and not win_api.is_own_window(self.last_external_hwnd)
        ):
            self.inserter.set_target(self.last_external_hwnd)
        elif not win_api.is_window(self.inserter.target_hwnd):
            self.inserter.clear()

    def _stop_recording(self) -> None:
        if self.state != "recording" or self.recorder is None:
            return
        self.state = "processing"
        self._cancel_duration_job()
        self.status_badge.set("Распознаю…", AMBER)
        self.footer_label.configure(text="Останавливаю запись и распознаю речь…")
        self._set_record_mode("busy")
        self.overlay.show_processing()
        self.recorder.stop()
        self._watchdog_job = self.root.after(120000, self._recognition_timeout)

    def _check_duration(self) -> None:
        self._duration_job = None
        if self.state != "recording":
            return
        elapsed = time.monotonic() - self._record_started_at
        if elapsed >= self.config.max_duration:
            self.footer_label.configure(
                text="Достигнут лимит длительности записи — распознаю."
            )
            self._stop_recording()
            return
        self._duration_job = self.root.after(1000, self._check_duration)

    def _recognition_timeout(self) -> None:
        self._watchdog_job = None
        if self.state != "processing":
            return
        self.state = "error"
        self._set_record_mode("start")
        self.status_badge.set("Не удалось", RED)
        self.overlay.show_error(
            "Распознавание заняло слишком много времени. Проверьте микрофон и попробуйте ещё раз.",
            retry=True,
        )
        self.footer_label.configure(text="Превышено время ожидания распознавания.")

    def _on_final(self, text: str) -> None:
        self._cancel_watchdog()
        if self.state != "processing":
            return
        formatted = format_transcript(
            text,
            voice_commands=self.config.voice_commands,
            punctuation=self.config.auto_punctuation,
        )
        if self.config.auto_learn:
            formatted = self.learning.apply(formatted)
        if not formatted:
            self.state = "error"
            self._set_record_mode("start")
            self.status_badge.set("Речь не распознана", AMBER)
            self.overlay.show_error(
                "Речь не распознана. Проверьте микрофон, говорите чуть громче и ближе к нему.",
                retry=True,
            )
            self.footer_label.configure(text="Пустой результат распознавания.")
            return

        self.last_text = formatted
        self._recognized_text = formatted
        self._show_last_text(formatted)
        if self.config.auto_insert:
            self.state = "idle"
            self._set_record_mode("start")
            self.status_badge.set("Вставляю…", AMBER)
            self.footer_label.configure(text="Вставляю текст в активное окно…")
            self.overlay.hide()
            self.root.update_idletasks()
            self._insert_text(formatted, auto=True)
            return

        self.state = "preview"
        self.status_badge.set("Текст готов", GREEN)
        self.footer_label.configure(
            text="Проверьте текст и нажмите «Вставить» или Ctrl+Enter."
        )
        self._set_record_mode("preview")
        self.overlay.show_preview(formatted)

    def _insert_current(self) -> None:
        if self.state != "preview":
            return
        text = self.overlay.get_text()
        if not text:
            self.overlay.show_error("Текст пуст — нечего вставлять.", retry=False)
            return
        if self.config.auto_learn and self._recognized_text:
            learned = self.learning.learn(self._recognized_text, text)
            if learned:
                self._update_learning_button()
                log.info("Запомнены исправления: %s", learned)
        self.last_text = text
        self._show_last_text(text)
        self.state = "inserting"
        self.overlay.hide()
        self.root.update_idletasks()
        self._insert_text(text, auto=False)

    def _insert_text(self, text: str, *, auto: bool) -> None:
        result = self.inserter.insert(text)
        self._recognized_text = ""
        if result.ok:
            self.state = "idle"
            self._set_record_mode("start")
            self.status_badge.set("Вставлено", GREEN)
            self.footer_label.configure(
                text=f"Текст вставлен в «{self.inserter.target_title or 'активное окно'}»."
            )
            return
        self.state = "error"
        self._set_record_mode("start")
        self.status_badge.set("Скопировано" if result.copied else "Ошибка", RED)
        self.footer_label.configure(text=result.reason)
        self.overlay.show_error(result.reason, retry=False)

    def _copy_current(self) -> None:
        if self.state != "preview":
            return
        text = self.overlay.get_text()
        if not text:
            return
        try:
            pyperclip.copy(text)
        except Exception as exc:
            messagebox.showerror(
                "Буфер обмена", f"Не удалось скопировать текст:\n{exc}", parent=self.root
            )
            return
        self.last_text = text
        self._show_last_text(text)
        self.overlay.show_copied()
        self.status_badge.set("Скопировано", GREEN)
        self.footer_label.configure(text="Текст скопирован в буфер обмена.")

    def _retry_recording(self) -> None:
        self._cancel_session(silent=True)
        self.root.after(30, lambda: self._start_recording(reuse_target=True))

    def _cancel_session(self, silent: bool = False) -> None:
        self.session_id += 1
        self._recognized_text = ""
        self._cancel_jobs()
        if self.recorder is not None:
            self.recorder.cancel()
            self.recorder = None
        self.overlay.hide()
        self.state = "idle"
        self._set_record_mode("start" if self.model is not None else "disabled")
        if self.model is not None:
            self.status_badge.set("Готово к работе", GREEN)
        if not silent:
            self.footer_label.configure(text="Запись отменена.")

    def _cancel_jobs(self) -> None:
        self._cancel_duration_job()
        self._cancel_watchdog()

    def _cancel_duration_job(self) -> None:
        if self._duration_job is not None:
            try:
                self.root.after_cancel(self._duration_job)
            except tk.TclError:
                pass
            self._duration_job = None

    def _cancel_watchdog(self) -> None:
        if self._watchdog_job is not None:
            try:
                self.root.after_cancel(self._watchdog_job)
            except tk.TclError:
                pass
            self._watchdog_job = None

    # --------------------------------------------------------------- события

    def _post(self, kind: str, *args) -> None:
        self.events.put((kind, args))

    def _poll_events(self) -> None:
        if self._closing:
            return
        try:
            while True:
                kind, args = self.events.get_nowait()
                self._handle_event(kind, args)
        except queue.Empty:
            pass
        self.root.after(45, self._poll_events)

    def _handle_event(self, kind: str, args: tuple) -> None:
        if kind == "hotkey":
            self._on_hotkey()
            return
        if kind == "tray_show":
            self._show_window()
            return
        if kind == "tray_record":
            self._tray_record()
            return
        if kind == "tray_exit":
            self._on_exit_requested()
            return
        if kind == "model_ready":
            self._on_model_ready(args[0])
            return
        if kind == "model_error":
            self._on_model_error(str(args[0]))
            return
        if kind == "download_progress":
            self._on_download_progress(int(args[0]), str(args[1]))
            return
        if kind == "download_ready":
            self._on_download_ready(Path(args[0]))
            return
        if kind == "download_error":
            self._on_download_error(str(args[0]))
            return

        if not args:
            return
        session = args[0]
        if session != self.session_id:
            return
        if kind == "partial":
            if self.state == "recording":
                self.overlay.set_partial(str(args[1]))
        elif kind == "level":
            if self.state == "recording":
                self.overlay.set_level(float(args[1]))
        elif kind == "final":
            if self.state == "processing":
                self._on_final(str(args[1]))
        elif kind == "audio_error":
            self._on_audio_error(str(args[1]))

    def _on_audio_error(self, message: str) -> None:
        if self.state not in {"recording", "processing"}:
            return
        self.state = "error"
        self._cancel_jobs()
        if self.recorder is not None:
            self.recorder.cancel()
            self.recorder = None
        self._set_record_mode("start")
        self.status_badge.set("Ошибка микрофона", RED)
        self.footer_label.configure(text="Ошибка записи. Выберите другой микрофон.")
        self.overlay.show_error(message, retry=True)

    def _on_hotkey(self) -> None:
        if self.state == "recording":
            self._stop_recording()
        elif self.state == "processing":
            return
        elif self.state == "preview":
            self._insert_current()
        elif self.state == "error":
            self._cancel_session()
        else:
            self._start_recording()

    # ---------------------------------------------------------------- прочее

    def _set_record_mode(self, mode: str) -> None:
        button = self.record_button
        if mode == "stop":
            button.configure(
                text="■   Остановить и распознать",
                bg=RED,
                activebackground="#FF6D7B",
                state="normal",
                cursor="hand2",
            )
        elif mode == "busy":
            button.configure(
                text="Распознаю…",
                bg=SURFACE_3,
                activebackground=SURFACE_3,
                state="disabled",
                cursor="arrow",
            )
        elif mode == "loading":
            button.configure(
                text="Загрузка модели…",
                bg=SURFACE_3,
                activebackground=SURFACE_3,
                state="disabled",
                cursor="arrow",
            )
        elif mode == "preview":
            button.configure(
                text="Проверьте текст в окне",
                bg=SURFACE_3,
                activebackground=SURFACE_3,
                state="disabled",
                cursor="arrow",
            )
        elif mode == "disabled":
            button.configure(
                text="Распознавание недоступно",
                bg=SURFACE_3,
                activebackground=SURFACE_3,
                state="disabled",
                cursor="arrow",
            )
        else:
            button.configure(
                text="●   Начать запись",
                bg=ACCENT,
                activebackground=ACCENT_HOVER,
                state="normal",
                cursor="hand2",
            )

    def _record_hover(self, entered: bool) -> None:
        if self.record_button["state"] == "disabled":
            return
        if self.record_button["state"] == "normal" and self.state == "recording":
            self.record_button.configure(bg="#FF6D7B" if entered else RED)
        else:
            self.record_button.configure(bg=ACCENT_HOVER if entered else ACCENT)

    def _show_last_text(self, text: str) -> None:
        self.last_text = text
        preview = text if len(text) <= 260 else text[:259].rstrip() + "…"
        self.last_text_label.configure(text=preview, fg=TEXT_SOFT)
        self.copy_last_button.configure(text="Копировать")
        if not self.copy_last_button.winfo_ismapped():
            self.copy_last_button.pack(side="right")

    def _copy_last_text(self) -> None:
        if not self.last_text:
            return
        try:
            pyperclip.copy(self.last_text)
        except Exception as exc:
            messagebox.showerror(
                "Буфер обмена", f"Не удалось скопировать текст:\n{exc}", parent=self.root
            )
            return
        self.footer_label.configure(text="Последняя расшифровка скопирована.")
        self.copy_last_button.configure(text="Скопировано")

    def _track_foreground(self) -> None:
        if self._closing:
            return
        hwnd = win_api.get_foreground_window()
        if (
            hwnd
            and win_api.is_window(hwnd)
            and not win_api.is_own_window(hwnd)
        ):
            title = win_api.get_window_title(hwnd)
            if title:
                self.last_external_hwnd = hwnd
                self.last_external_title = title
        self.root.after(350, self._track_foreground)

    def _start_minimized(self) -> None:
        if self.tray.available:
            self.root.withdraw()
        else:
            self.root.iconify()

    def _show_window(self) -> None:
        if self._closing:
            return
        self.root.deiconify()
        try:
            self.root.state("normal")
        except tk.TclError:
            pass
        self.root.lift()
        self.root.focus_force()
        try:
            self.root.attributes("-topmost", True)
            self.root.after(250, lambda: self.root.attributes("-topmost", False))
        except tk.TclError:
            pass

    def _tray_record(self) -> None:
        if self.model is None:
            self._show_window()
            self.status_badge.set("Модель не готова", AMBER)
            self.footer_label.configure(text="Дождитесь загрузки модели.")
            return
        if self.state == "recording":
            self._stop_recording()
        elif self.state == "preview":
            self._insert_current()
        elif self.state == "idle":
            self._start_recording()
        elif self.state == "error":
            self._cancel_session()

    def _on_close(self) -> None:
        """Закрытие окна сворачивает программу в трей, а не завершает её."""
        if not self.tray.available:
            self._on_exit_requested()
            return
        if self.state not in {"recording", "processing"}:
            self._cancel_session(silent=True)
        self._save_config()
        self.root.withdraw()
        if not self._tray_hint_shown:
            self._tray_hint_shown = True
            self.tray.notify(
                "Программа свёрнута в трей. Горячая клавиша продолжает работать."
            )
        log.info("Окно скрыто в трей")

    def _on_exit_requested(self) -> None:
        if self.state in {"recording", "processing"}:
            if not messagebox.askyesno(
                "Голосовой ввод",
                "Идёт запись. Закрыть программу и отменить её?",
                parent=self.root,
            ):
                return
        self._quit_app()

    def _quit_app(self) -> None:
        if self._closing:
            return
        self._closing = True
        self.session_id += 1
        self._cancel_jobs()
        if self.recorder is not None:
            self.recorder.cancel()
            self.recorder = None
        try:
            self.hotkey.shutdown()
        except Exception:
            log.exception("Ошибка при отключении горячей клавиши")
        try:
            self.tray.stop()
        except Exception:
            log.exception("Ошибка при остановке трея")
        self._save_config()
        self.overlay.destroy()
        self.root.destroy()


def _single_instance_guard() -> int | None:
    """Не даёт запустить две копии: иначе конфликтуют горячие клавиши."""
    import ctypes
    import ctypes.wintypes as wt

    kernel32 = ctypes.windll.kernel32
    user32 = ctypes.windll.user32
    kernel32.CreateMutexW.argtypes = (wt.LPVOID, wt.BOOL, wt.LPCWSTR)
    kernel32.CreateMutexW.restype = wt.HANDLE
    handle = kernel32.CreateMutexW(None, False, "Local\\VoiceInputRU.SingleInstance")
    if not handle:
        return None
    if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        hwnd = user32.FindWindowW(None, f"{APP_TITLE} — русская речь в текст")
        if hwnd:
            user32.ShowWindow(hwnd, win_api.SW_SHOW)
            user32.ShowWindow(hwnd, win_api.SW_RESTORE)
            user32.SetForegroundWindow(hwnd)
            user32.FlashWindow(hwnd, True)
        else:
            user32.MessageBoxW(
                None,
                "Голосовой ввод уже запущен.\n"
                "Окно программы должно быть на панели задач.",
                APP_TITLE,
                0x00000040 | 0x00040000,
            )
        return 0
    return None


def main() -> int:
    import logging

    from .paths import setup_logging

    log_path = setup_logging()
    log = logging.getLogger(__name__)
    log.info("=== Запуск %s, лог: %s ===", VERSION, log_path)

    win_api.enable_dpi_awareness()
    win_api.set_app_user_model_id()

    already_running = _single_instance_guard()
    if already_running is not None:
        return already_running

    root = tk.Tk()
    app = VoiceInputApp(root)

    def on_error(exc_type, exc_value, exc_tb):
        log.exception("Необработанная ошибка", exc_info=(exc_type, exc_value, exc_tb))
        try:
            messagebox.showerror(
                "Голосовой ввод",
                f"Произошла ошибка:\n{exc_value}\n\nПодробности в журнале.",
                parent=root,
            )
        except Exception:
            pass

    root.report_callback_exception = on_error
    try:
        root.mainloop()
    finally:
        try:
            app.hotkey.shutdown()
        except Exception:
            pass
        log.info("Приложение завершено")
    return 0

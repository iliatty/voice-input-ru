"""Пути приложения, поиск модели и логирование."""
from __future__ import annotations

import logging
import logging.handlers
import os
import sys
import tempfile
from pathlib import Path

APP_NAME = "VoiceInputRU"
APP_TITLE = "Голосовой ввод"
VERSION = "1.2.0"
MODEL_FOLDER_NAME = "faster-whisper-small"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    """Папка рядом с exe (или корень исходников)."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def bundle_dir() -> Path:
    """Папка ресурсов PyInstaller (в one-folder это _internal)."""
    meipass = getattr(sys, "_MEIPASS", None)
    return Path(meipass) if meipass else app_dir()


def data_dir() -> Path:
    base = os.environ.get("APPDATA")
    if base:
        path = Path(base) / APP_NAME
    else:
        path = Path.home() / f".{APP_NAME.lower()}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def local_models_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        path = Path(base) / APP_NAME / "models"
    else:
        path = data_dir() / "models"
    path.mkdir(parents=True, exist_ok=True)
    return path


def is_writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path, prefix=".write-test-", delete=True):
            pass
        return True
    except OSError:
        return False


def model_install_dir() -> Path:
    """Куда скачивать модель, если её нет рядом с программой."""
    preferred = app_dir() / "models"
    if is_writable(preferred):
        return preferred
    return local_models_dir()


def model_is_valid(path: Path | str | None) -> bool:
    if not path:
        return False
    root = Path(path)
    if not root.is_dir():
        return False
    return (
        (root / "model.bin").is_file()
        and (root / "config.json").is_file()
        and (root / "tokenizer.json").is_file()
        and (root / "vocabulary.txt").is_file()
    )


def find_model_dir(preferred: str | Path | None = None) -> Path | None:
    candidates: list[Path] = []
    if preferred:
        candidates.append(Path(preferred))
    candidates.extend(
        [
            app_dir() / "models" / MODEL_FOLDER_NAME,
            bundle_dir() / "models" / MODEL_FOLDER_NAME,
            data_dir() / "models" / MODEL_FOLDER_NAME,
            local_models_dir() / MODEL_FOLDER_NAME,
        ]
    )
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate).lower()
        if key in seen:
            continue
        seen.add(key)
        if model_is_valid(candidate):
            return candidate
    return None


def resource_path(relative: str) -> Path:
    return bundle_dir() / relative


def setup_logging() -> Path:
    log_path = data_dir() / "voice_input.log"
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    already = False
    for existing in root.handlers:
        filename = getattr(existing, "baseFilename", None)
        if filename and Path(filename).resolve() == log_path.resolve():
            already = True
            break
    if not already:
        handler: logging.Handler | None = None
        try:
            handler = logging.handlers.RotatingFileHandler(
                log_path,
                maxBytes=1_500_000,
                backupCount=3,
                encoding="utf-8",
            )
        except OSError:
            try:
                handler = logging.FileHandler(log_path, encoding="utf-8")
            except OSError:
                handler = None
        if handler is not None:
            handler.setFormatter(formatter)
            root.addHandler(handler)
    return log_path

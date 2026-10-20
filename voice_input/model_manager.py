"""Загрузка офлайн-модели faster-whisper и её скачивание при необходимости."""
from __future__ import annotations

import logging
import os
import shutil
import threading
from pathlib import Path
from typing import Callable

import requests

from .paths import MODEL_FOLDER_NAME, model_install_dir, model_is_valid

log = logging.getLogger(__name__)

MODEL_BASES = (
    "https://huggingface.co/Systran/faster-whisper-small/resolve/main/",
    "https://hf-mirror.com/Systran/faster-whisper-small/resolve/main/",
)
MODEL_FILES: tuple[tuple[str, int], ...] = (
    ("config.json", 2_370),
    ("model.bin", 483_546_902),
    ("tokenizer.json", 2_203_239),
    ("vocabulary.txt", 459_861),
)
MODEL_SIZE = sum(size for _, size in MODEL_FILES)


def load_model_async(
    model_path: Path,
    on_ready: Callable[[object], None],
    on_error: Callable[[str], None],
) -> None:
    def worker() -> None:
        try:
            from faster_whisper import WhisperModel

            log.info("Загрузка модели Whisper: %s", model_path)
            # CTranslate2, как и Vosk, не любит абсолютные пути с кириллицей.
            # Открываем модель из её папки, а затем возвращаем рабочий каталог.
            previous = os.getcwd()
            try:
                os.chdir(model_path)
                model = WhisperModel(
                    ".",
                    device="cpu",
                    compute_type="int8",
                    cpu_threads=max(4, min(8, os.cpu_count() or 4)),
                    num_workers=1,
                )
            finally:
                try:
                    os.chdir(previous)
                except OSError:
                    pass
            log.info("Модель Whisper загружена")
            on_ready(model)
        except Exception as exc:
            log.exception("Не удалось загрузить модель Whisper")
            on_error(str(exc))

    threading.Thread(target=worker, name="model-loader", daemon=True).start()


def download_model_async(
    on_progress: Callable[[int, str], None],
    on_ready: Callable[[Path], None],
    on_error: Callable[[str], None],
) -> None:
    def worker() -> None:
        target_root = model_install_dir()
        destination = target_root / MODEL_FOLDER_NAME
        temp = target_root / f"_{MODEL_FOLDER_NAME}-download"
        errors: list[str] = []
        try:
            if model_is_valid(destination):
                on_ready(destination)
                return
            if temp.exists():
                shutil.rmtree(temp, ignore_errors=True)
            temp.mkdir(parents=True, exist_ok=True)
            for base in MODEL_BASES:
                try:
                    _download_all(base, temp, on_progress)
                    if not model_is_valid(temp):
                        raise ValueError("Файлы модели скачались не полностью")
                    if destination.exists():
                        shutil.rmtree(destination, ignore_errors=True)
                    shutil.move(str(temp), str(destination))
                    on_ready(destination)
                    return
                except Exception as exc:
                    log.exception("Не удалось скачать модель Whisper с %s", base)
                    errors.append(str(exc))
                    for child in temp.iterdir():
                        try:
                            if child.is_file():
                                child.unlink()
                        except OSError:
                            pass
            on_error(
                "Не удалось скачать модель Whisper.\n"
                "Проверьте интернет или скачайте папку faster-whisper-small вручную.\n\n"
                + (errors[-1] if errors else "")
            )
        except Exception as exc:
            log.exception("Ошибка загрузки модели Whisper")
            on_error(str(exc))

    threading.Thread(target=worker, name="model-downloader", daemon=True).start()


def _download_all(
    base: str,
    destination: Path,
    on_progress: Callable[[int, str], None],
) -> None:
    downloaded = 0
    for filename, expected_size in MODEL_FILES:
        on_progress(
            int(downloaded * 100 / MODEL_SIZE),
            f"Скачивание модели… {downloaded // (1024 * 1024)} МБ",
        )
        path = destination / filename
        part = destination / f"{filename}.part"
        with requests.get(
            base + filename,
            stream=True,
            timeout=(30, 240),
        ) as response:
            response.raise_for_status()
            with part.open("wb") as file:
                for chunk in response.iter_content(chunk_size=1024 * 512):
                    if not chunk:
                        continue
                    file.write(chunk)
                    downloaded += len(chunk)
                    percent = min(99, int(downloaded * 100 / MODEL_SIZE))
                    if percent % 2 == 0:
                        on_progress(
                            percent,
                            f"Скачивание модели… {downloaded // (1024 * 1024)} МБ",
                        )
        if part.stat().st_size < expected_size * 0.95:
            raise ValueError(f"Файл {filename} скачался не полностью")
        os.replace(part, path)
    on_progress(100, "Модель скачана")

"""Загрузка офлайн-модели Vosk и её скачивание при необходимости."""
from __future__ import annotations

import logging
import os
import shutil
import threading
import zipfile
from pathlib import Path
from typing import Callable

import requests

from .paths import MODEL_FOLDER_NAME, model_install_dir, model_is_valid

log = logging.getLogger(__name__)

MODEL_URLS = (
    "https://huggingface.co/localstack/vosk-models/resolve/main/vosk-model-small-ru-0.22.zip",
    "https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip",
)
MODEL_SIZE = 46_236_750


def load_model_async(
    model_path: Path,
    on_ready: Callable[[object], None],
    on_error: Callable[[str], None],
) -> None:
    def worker() -> None:
        try:
            import vosk

            vosk.SetLogLevel(-1)
            log.info("Загрузка модели Vosk: %s", model_path)
            # Vosk (C++ слой) не открывает абсолютные пути с кириллицей.
            # Открываем модель как "." из её папки — это надёжно и для
            # путей вида C:\Users\Иван\...
            previous = os.getcwd()
            try:
                os.chdir(model_path)
                model = vosk.Model(".")
            finally:
                try:
                    os.chdir(previous)
                except OSError:
                    pass
            log.info("Модель загружена")
            on_ready(model)
        except Exception as exc:
            log.exception("Не удалось загрузить модель")
            on_error(str(exc))

    threading.Thread(target=worker, name="model-loader", daemon=True).start()


def _safe_extract(archive: zipfile.ZipFile, destination: Path) -> None:
    destination = destination.resolve()
    for member in archive.infolist():
        target = (destination / member.filename).resolve()
        if destination not in target.parents and target != destination:
            raise ValueError("Архив содержит недопустимый путь")
    archive.extractall(destination)


def download_model_async(
    on_progress: Callable[[int, str], None],
    on_ready: Callable[[Path], None],
    on_error: Callable[[str], None],
) -> None:
    def worker() -> None:
        target_root = model_install_dir()
        archive_path = target_root / f"{MODEL_FOLDER_NAME}.zip.part"
        extract_dir = target_root / "_extract"
        errors: list[str] = []
        try:
            for url in MODEL_URLS:
                try:
                    on_progress(0, "Скачивание модели…")
                    log.info("Скачивание модели: %s", url)
                    _download(url, archive_path, on_progress)
                    on_progress(100, "Распаковка модели…")
                    if extract_dir.exists():
                        shutil.rmtree(extract_dir, ignore_errors=True)
                    with zipfile.ZipFile(archive_path) as archive:
                        _safe_extract(archive, extract_dir)
                    source = extract_dir / MODEL_FOLDER_NAME
                    if not model_is_valid(source):
                        raise ValueError("В архиве нет ожидаемой модели")
                    destination = target_root / MODEL_FOLDER_NAME
                    if destination.exists():
                        shutil.rmtree(destination, ignore_errors=True)
                    shutil.move(str(source), str(destination))
                    shutil.rmtree(extract_dir, ignore_errors=True)
                    archive_path.unlink(missing_ok=True)
                    if not model_is_valid(destination):
                        raise ValueError("Модель распаковалась не полностью")
                    on_ready(destination)
                    return
                except Exception as exc:
                    log.exception("Не удалось скачать модель с %s", url)
                    errors.append(str(exc))
                    archive_path.unlink(missing_ok=True)
            on_error(
                "Не удалось скачать модель.\n"
                "Проверьте подключение к интернету или скачайте модель вручную.\n\n"
                + (errors[-1] if errors else "")
            )
        except Exception as exc:
            log.exception("Ошибка скачивания модели")
            on_error(str(exc))

    threading.Thread(target=worker, name="model-downloader", daemon=True).start()


def _download(
    url: str,
    destination: Path,
    on_progress: Callable[[int, str], None],
) -> None:
    with requests.get(url, stream=True, timeout=(20, 120)) as response:
        response.raise_for_status()
        total = int(response.headers.get("content-length") or MODEL_SIZE)
        downloaded = 0
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("wb") as file:
            for chunk in response.iter_content(chunk_size=1024 * 256):
                if not chunk:
                    continue
                file.write(chunk)
                downloaded += len(chunk)
                percent = int(downloaded * 100 / max(1, total))
                if percent % 2 == 0:
                    on_progress(
                        min(99, percent),
                        f"Скачивание модели… {downloaded // (1024 * 1024)} МБ",
                    )
    if destination.stat().st_size < 1_000_000:
        raise ValueError("Файл модели слишком маленький")

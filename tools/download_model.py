"""Скачивает русскую модель Vosk в models/ для сборки или запуска из исходников."""
from __future__ import annotations

import shutil
import sys
import zipfile
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
MODEL = "vosk-model-small-ru-0.22"
URLS = (
    "https://huggingface.co/localstack/vosk-models/resolve/main/vosk-model-small-ru-0.22.zip",
    "https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip",
)


def main() -> int:
    target = ROOT / "models" / MODEL
    if (target / "am").is_dir():
        print(f"Модель уже есть: {target}")
        return 0

    models = ROOT / "models"
    models.mkdir(parents=True, exist_ok=True)
    archive = models / f"{MODEL}.zip.part"
    extract = models / "_extract"

    for url in URLS:
        try:
            print(f"Скачивание: {url}")
            with requests.get(url, stream=True, timeout=(20, 180)) as response:
                response.raise_for_status()
                total = int(response.headers.get("content-length") or 46_236_750)
                done = 0
                with archive.open("wb") as file:
                    for chunk in response.iter_content(1024 * 256):
                        if not chunk:
                            continue
                        file.write(chunk)
                        done += len(chunk)
                        percent = int(done * 100 / total)
                        if percent % 5 == 0:
                            print(f"\r{percent:3d}%  {done // (1024 * 1024)} МБ", end="")
            print()
            if extract.exists():
                shutil.rmtree(extract, ignore_errors=True)
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(extract)
            source = extract / MODEL
            if not (source / "am").is_dir():
                raise RuntimeError("в архиве нет ожидаемой модели")
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
            shutil.move(str(source), str(target))
            shutil.rmtree(extract, ignore_errors=True)
            archive.unlink(missing_ok=True)
            print(f"Готово: {target}")
            return 0
        except Exception as exc:
            print(f"\nНе удалось: {exc}")
            archive.unlink(missing_ok=True)

    print("Не удалось скачать модель. Проверьте интернет.")
    return 1


if __name__ == "__main__":
    sys.exit(main())

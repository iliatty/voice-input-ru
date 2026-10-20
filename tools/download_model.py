"""Скачивает русскую модель faster-whisper small в models/."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
MODEL = "faster-whisper-small"
BASES = (
    "https://huggingface.co/Systran/faster-whisper-small/resolve/main/",
    "https://hf-mirror.com/Systran/faster-whisper-small/resolve/main/",
)
FILES = {
    "config.json": 2_370,
    "model.bin": 483_546_902,
    "tokenizer.json": 2_203_239,
    "vocabulary.txt": 459_861,
}


def main() -> int:
    target = ROOT / "models" / MODEL
    if (target / "model.bin").is_file():
        print(f"Модель уже есть: {target}")
        return 0

    temp = ROOT / "models" / f"_{MODEL}-download"
    if temp.exists():
        shutil.rmtree(temp, ignore_errors=True)
    temp.mkdir(parents=True, exist_ok=True)
    total = sum(FILES.values())
    done = 0
    for base in BASES:
        try:
            for name, expected in FILES.items():
                print(f"\n{name} ...", end="", flush=True)
                part = temp / f"{name}.part"
                with requests.get(base + name, stream=True, timeout=(30, 240)) as response:
                    response.raise_for_status()
                    with part.open("wb") as file:
                        for chunk in response.iter_content(1024 * 512):
                            if not chunk:
                                continue
                            file.write(chunk)
                            done += len(chunk)
                            if done % (1024 * 1024) < 512 * 1024:
                                print(f"\r{int(done * 100 / total):3d}%", end="", flush=True)
                if part.stat().st_size < expected * 0.95:
                    raise RuntimeError(f"{name} скачался не полностью")
                part.replace(temp / name)
            if not (temp / "model.bin").is_file():
                raise RuntimeError("нет model.bin")
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
            shutil.move(str(temp), str(target))
            print(f"\nГотово: {target}")
            return 0
        except Exception as exc:
            print(f"\nНе удалось: {exc}")
            for child in temp.iterdir():
                if child.is_file():
                    child.unlink(missing_ok=True)

    print("Не удалось скачать модель. Проверьте интернет.")
    return 1


if __name__ == "__main__":
    sys.exit(main())

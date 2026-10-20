"""Запуск без консольного окна."""
from __future__ import annotations

import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
VENDOR = BASE_DIR / "vendor"
if VENDOR.is_dir():
    sys.path.insert(0, str(VENDOR))
    pywin32 = VENDOR / "pywin32_system32"
    if pywin32.is_dir():
        try:
            os.add_dll_directory(str(pywin32))
        except (AttributeError, OSError):
            pass

from voice_input.app import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())

"""Собирает assets/app.ico из PNG-файлов разных размеров."""
from __future__ import annotations

import struct
from pathlib import Path

SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]
ASSETS = Path(__file__).resolve().parent.parent / "assets"


def main() -> None:
    images = []
    for size in SIZES:
        path = ASSETS / f"icon-{size}.png"
        images.append((size, path.read_bytes()))

    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries = []
    payload = b""
    for size, data in images:
        width = 0 if size >= 256 else size
        height = 0 if size >= 256 else size
        entries.append(
            struct.pack(
                "<BBBBHHII",
                width,
                height,
                0,
                0,
                1,
                32,
                len(data),
                offset,
            )
        )
        offset += len(data)
        payload += data

    (ASSETS / "app.ico").write_bytes(header + b"".join(entries) + payload)
    print(f"app.ico: {len(header + b''.join(entries) + payload)} bytes")


if __name__ == "__main__":
    main()

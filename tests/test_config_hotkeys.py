from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from voice_input.config import AppConfig, ConfigStore
from voice_input.hotkeys import format_hotkey, normalize_hotkey, validate_hotkey


class ConfigTests(unittest.TestCase):
    def test_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.json"
            store = ConfigStore(path)
            config = AppConfig(
                device_key="Mic|WASAPI",
                hotkey="ctrl+shift+f9",
                auto_insert=True,
                auto_punctuation=False,
                voice_commands=False,
                start_with_windows=True,
                model_dir="C:/models/ru",
                max_duration=120,
            )
            store.save(config)
            loaded = store.load()
            self.assertEqual(loaded, config)

    def test_corrupt_file_falls_back(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.json"
            path.write_text("{not json", encoding="utf-8")
            loaded = ConfigStore(path).load()
            self.assertEqual(loaded.hotkey, "ctrl+alt+space")
            self.assertTrue(list(Path(folder).glob("config.broken-*.json")))


class HotkeyTests(unittest.TestCase):
    def test_normalize(self) -> None:
        self.assertEqual(normalize_hotkey("Ctrl + Alt + Space"), "ctrl+alt+space")
        self.assertEqual(normalize_hotkey("ALT+CTRL+space"), "ctrl+alt+space")

    def test_format(self) -> None:
        self.assertEqual(format_hotkey("ctrl+alt+space"), "Ctrl + Alt + Space")
        self.assertEqual(format_hotkey("ctrl+shift+f9"), "Ctrl + Shift + F9")

    def test_validate(self) -> None:
        self.assertTrue(validate_hotkey("ctrl+alt+space")[0])
        self.assertTrue(validate_hotkey("ctrl+shift+f9")[0])
        self.assertFalse(validate_hotkey("space")[0])
        self.assertFalse(validate_hotkey("ctrl")[0])


if __name__ == "__main__":
    unittest.main()

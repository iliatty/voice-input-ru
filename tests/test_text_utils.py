from __future__ import annotations

import unittest

from voice_input.text_utils import _normalize_spaces, format_transcript


class FormatTranscriptTests(unittest.TestCase):
    def test_plain_text(self) -> None:
        self.assertEqual(
            format_transcript("привет это проверка распознавания"),
            "Привет это проверка распознавания.",
        )

    def test_spoken_punctuation(self) -> None:
        self.assertEqual(
            format_transcript("привет запятая как дела вопросительный знак"),
            "Привет, как дела?",
        )

    def test_new_line(self) -> None:
        self.assertEqual(
            format_transcript("первая строка новая строка вторая строка"),
            "Первая строка\nВторая строка.",
        )

    def test_quotes(self) -> None:
        self.assertEqual(
            format_transcript("открыть кавычки привет закрыть кавычки"),
            "«Привет».",
        )

    def test_word_tochka_is_not_punctuation(self) -> None:
        self.assertEqual(format_transcript("точка зрения"), "Точка зрения.")

    def test_final_tochka_command(self) -> None:
        self.assertEqual(format_transcript("привет точка"), "Привет.")

    def test_whisper_punctuation_preserved(self) -> None:
        self.assertEqual(
            format_transcript("Привет. Это проверка распознавания."),
            "Привет. Это проверка распознавания.",
        )

    def test_command_with_existing_punctuation(self) -> None:
        self.assertEqual(
            format_transcript("Привет, запятая, как дела?"),
            "Привет, как дела?",
        )
        self.assertEqual(format_transcript("Привет точка."), "Привет.")

    def test_dash(self) -> None:
        self.assertEqual(format_transcript("привет тире мир"), "Привет — мир.")

    def test_trailing_comma_becomes_period(self) -> None:
        self.assertEqual(format_transcript("привет запятая"), "Привет.")

    def test_punctuation_disabled(self) -> None:
        self.assertEqual(
            format_transcript("привет как дела", punctuation=False),
            "привет как дела",
        )

    def test_voice_commands_disabled(self) -> None:
        self.assertEqual(
            format_transcript("привет запятая как дела", voice_commands=False),
            "Привет запятая как дела.",
        )

    def test_multiple_spaces(self) -> None:
        self.assertEqual(
            format_transcript("привет    мир"),
            "Привет мир.",
        )

    def test_empty(self) -> None:
        self.assertEqual(format_transcript(""), "")


class NormalizeSpacesTests(unittest.TestCase):
    def test_space_before_punctuation(self) -> None:
        self.assertEqual(_normalize_spaces("а , б"), "а, б")


if __name__ == "__main__":
    unittest.main()

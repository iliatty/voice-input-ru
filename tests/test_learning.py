from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from voice_input.learning import LearningStore


class LearningStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / "learning.json"

    def tearDown(self) -> None:
        self.folder.cleanup()

    def test_learns_word_replacement(self) -> None:
        store = LearningStore(self.path)
        learned = store.learn("привет хат как дела", "привет чат как дела")
        self.assertEqual(learned, [("хат", "чат")])
        self.assertEqual(store.apply("привет хат"), "привет чат")
        self.assertEqual(store.count, 1)

    def test_ignores_case_and_punctuation_only(self) -> None:
        store = LearningStore(self.path)
        store.learn("привет как дела", "Привет, как дела?")
        self.assertEqual(store.count, 0)

    def test_ignores_stopwords(self) -> None:
        store = LearningStore(self.path)
        store.learn("я в дом", "я во дом")
        self.assertEqual(store.count, 0)

    def test_persists(self) -> None:
        store = LearningStore(self.path)
        store.learn("привет хат", "привет чат")
        loaded = LearningStore(self.path)
        self.assertEqual(loaded.count, 1)
        self.assertEqual(loaded.apply("хат"), "чат")

    def test_phrase_replacement(self) -> None:
        store = LearningStore(self.path)
        store.learn("открой новую почту", "открой новый имейл")
        self.assertEqual(store.apply("открой новую почту"), "открой новый имейл")

    def test_does_not_replace_inside_word(self) -> None:
        store = LearningStore(self.path)
        store.learn("хат", "чат")
        self.assertEqual(store.apply("шахта"), "шахта")

    def test_remove_and_clear(self) -> None:
        store = LearningStore(self.path)
        store.learn("хат", "чат")
        self.assertTrue(store.remove("хат"))
        self.assertEqual(store.count, 0)
        store.learn("хат", "чат")
        store.clear()
        self.assertEqual(store.count, 0)


if __name__ == "__main__":
    unittest.main()

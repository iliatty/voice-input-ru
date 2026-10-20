"""Самообучение словаря по исправлениям пользователя.

Whisper нельзя дообучить «на лету» без датасета и отдельного пайплайна, но можно
запоминать устойчивые замены слов, которые пользователь делает в предпросмотре,
и применять их к следующим расшифровкам. Это дешёвая адаптация под словарь
конкретного человека: имена, термины, сленг.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from .paths import data_dir

log = logging.getLogger(__name__)

TOKEN_RE = re.compile(r"[А-Яа-яЁёA-Za-z0-9]+(?:-[А-Яа-яЁёA-Za-z0-9]+)?")
_STOPWORDS = {
    "и",
    "в",
    "во",
    "не",
    "на",
    "с",
    "со",
    "а",
    "но",
    "что",
    "как",
    "это",
    "я",
    "ты",
    "он",
    "она",
    "мы",
    "вы",
    "они",
    "да",
    "нет",
    "же",
    "ли",
    "бы",
    "по",
    "из",
    "от",
    "до",
    "за",
    "для",
    "при",
    "о",
    "об",
    "у",
    "к",
    "ко",
    "или",
    "то",
    "так",
    "там",
    "тут",
    "вот",
    "ну",
    "уже",
    "ещё",
    "еще",
    "только",
    "очень",
}
MAX_PAIRS = 400


@dataclass
class LearnedPair:
    wrong: str
    correct: str
    count: int = 1
    updated: float = 0.0

    def as_dict(self) -> dict:
        return {
            "wrong": self.wrong,
            "correct": self.correct,
            "count": self.count,
            "updated": self.updated,
        }


class LearningStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (data_dir() / "learning.json")
        self._pairs: dict[tuple[str, str], LearnedPair] = {}
        self.load()

    @property
    def count(self) -> int:
        return len(self._pairs)

    def pairs(self) -> list[LearnedPair]:
        return sorted(
            self._pairs.values(),
            key=lambda pair: (-pair.count, pair.wrong.casefold()),
        )

    def load(self) -> None:
        if not self.path.is_file():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            for item in raw.get("pairs", []):
                wrong = str(item.get("wrong", "")).strip()
                correct = str(item.get("correct", "")).strip()
                if not wrong or not correct:
                    continue
                key = (wrong.casefold(), correct.casefold())
                self._pairs[key] = LearnedPair(
                    wrong=wrong,
                    correct=correct,
                    count=max(1, int(item.get("count", 1))),
                    updated=float(item.get("updated", 0.0)),
                )
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            log.warning("Не удалось прочитать словарь обучения: %s", exc)
            self._pairs = {}

    def save(self) -> bool:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "pairs": [
                            pair.as_dict() for pair in self.pairs()[:MAX_PAIRS]
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            os.replace(tmp, self.path)
            return True
        except OSError as exc:
            log.warning("Не удалось сохранить словарь обучения: %s", exc)
            return False

    def add(self, wrong: str, correct: str, count: int = 1) -> bool:
        wrong = " ".join(wrong.split())
        correct = " ".join(correct.split())
        if not wrong or not correct or wrong.casefold() == correct.casefold():
            return False
        key = (wrong.casefold(), correct.casefold())
        existing = self._pairs.get(key)
        if existing is None:
            self._pairs[key] = LearnedPair(
                wrong=wrong,
                correct=correct,
                count=max(1, count),
                updated=time.time(),
            )
            return True
        existing.count += max(1, count)
        existing.updated = time.time()
        return False

    def learn(self, before: str, after: str) -> list[tuple[str, str]]:
        """Сравнивает распознанный и исправленный текст, запоминает замены."""
        before_tokens = TOKEN_RE.findall(before or "")
        after_tokens = TOKEN_RE.findall(after or "")
        if not before_tokens or not after_tokens:
            return []
        if abs(len(before_tokens) - len(after_tokens)) > max(
            3, len(before_tokens) // 2
        ):
            return []

        matcher = SequenceMatcher(
            None,
            [token.casefold() for token in before_tokens],
            [token.casefold() for token in after_tokens],
            autojunk=False,
        )
        learned: list[tuple[str, str]] = []
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag != "replace":
                continue
            wrong_tokens = before_tokens[i1:i2]
            correct_tokens = after_tokens[j1:j2]
            if not wrong_tokens or not correct_tokens:
                continue
            if len(wrong_tokens) > 2 or len(correct_tokens) > 2:
                continue
            wrong = " ".join(wrong_tokens).strip()
            correct = " ".join(correct_tokens).strip()
            if not self._is_learnable(wrong, correct):
                continue
            self.add(wrong, correct)
            learned.append((wrong, correct))

        if learned:
            self.save()
            log.info("Автообучение: запомнено замен %s", len(learned))
        return learned

    @staticmethod
    def _is_learnable(wrong: str, correct: str) -> bool:
        wrong_key = wrong.casefold()
        correct_key = correct.casefold()
        if wrong_key == correct_key:
            return False
        if len(wrong_key) < 2 or len(correct_key) < 2:
            return False
        if wrong_key in _STOPWORDS or correct_key in _STOPWORDS:
            return False
        if all(token in _STOPWORDS for token in wrong_key.split()):
            return False
        return True

    def apply(self, text: str) -> str:
        if not text or not self._pairs:
            return text
        result = text
        ordered = sorted(
            self._pairs.values(),
            key=lambda pair: (-len(pair.wrong.split()), -len(pair.wrong)),
        )
        for pair in ordered:
            words = [re.escape(word) for word in pair.wrong.split()]
            pattern = (
                r"(?<![\w-])" + r"\s+".join(words) + r"(?![\w-])"
            )
            try:
                result = re.sub(
                    pattern,
                    lambda match, value=pair.correct: self._match_case(
                        match.group(0), value
                    ),
                    result,
                    flags=re.IGNORECASE,
                )
            except re.error:
                log.debug("Некорректная пара обучения: %s", pair.wrong)
        return result

    @staticmethod
    def _match_case(source: str, replacement: str) -> str:
        if source and source[0].isupper() and replacement:
            return replacement[0].upper() + replacement[1:]
        return replacement

    def remove(self, wrong: str, correct: str | None = None) -> bool:
        wrong_key = wrong.casefold()
        correct_key = correct.casefold() if correct is not None else None
        removed = False
        for key in list(self._pairs):
            if key[0] == wrong_key and (correct_key is None or key[1] == correct_key):
                del self._pairs[key]
                removed = True
        if removed:
            self.save()
        return removed

    def clear(self) -> None:
        self._pairs.clear()
        self.save()

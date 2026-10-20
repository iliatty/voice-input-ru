"""Приведение текста распознавания к аккуратному виду и команды пунктуации."""
from __future__ import annotations

import re

# Порядок важен: длинные команды обрабатываются раньше коротких.
_COMMANDS: tuple[tuple[str, str], ...] = (
    (r"\bточка\s+с\s+запятой\b", ";"),
    (r"\bвопросительный\s+знак\b", "?"),
    (r"\bвосклицательный\s+знак\b", "!"),
    (r"\bновая\s+строка\b", "\n"),
    (r"\bс\s+новой\s+строки\b", "\n"),
    (r"\bновый\s+абзац\b", "\n\n"),
    (r"\bновый\s+параграф\b", "\n\n"),
    (r"\bабзац\b", "\n\n"),
    (r"\bоткрыть\s+кавычки\b", "«"),
    (r"\bзакрыть\s+кавычки\b", "»"),
    (r"\bоткрыть\s+скобку\b", "("),
    (r"\bзакрыть\s+скобку\b", ")"),
    (r"\bдвоеточие\b", ":"),
    (r"\bзапятая\b", ","),
    (r"\bтире\b", " — "),
    (r"\bдефис\b", "-"),
)

_SENTENCE_RE = re.compile(
    r"(^|[.!?]\s+|\n+)([«\"'(\[]*)([а-яёa-z])",
    re.IGNORECASE,
)


def apply_voice_commands(text: str) -> str:
    result = text
    for pattern, replacement in _COMMANDS:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    # «точка» как команда — только если это последнее слово фразы.
    # Whisper может добавить свою точку после слова-команды.
    result = re.sub(
        r"(^|\s)точка\s*[.!?]?\s*$",
        ".",
        result,
        flags=re.IGNORECASE,
    )
    return result


def _normalize_spaces(text: str) -> str:
    text = text.replace("\xa0", " ").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Перед знаками препинания пробел не нужен.
    text = re.sub(r"[ \t]+([,.;:?!»)\]}])", r"\1", text)
    # После знака препинания — ровно один пробел, если дальше идёт текст.
    text = re.sub(r"([,.;:?!])(?=[^\s\n,.;:?!»)\]])", r"\1 ", text)
    # Тире с пробелами с обеих сторон.
    text = re.sub(r"\s*—\s*", " — ", text)
    # Whisper мог уже поставить знак рядом со словом-командой.
    text = re.sub(r"([,;:])\s*\1+", r"\1", text)
    text = re.sub(r"[,;:]\s*([.!?])", r"\1", text)
    text = re.sub(r"([.!?])\s*[,;:]+", r"\1", text)
    text = re.sub(r"([«\"'(\[])\s+", r"\1", text)
    text = re.sub(r"\s+([»\"')\]])", r"\1", text)
    return text.strip()


def _capitalize_sentences(text: str) -> str:
    def upper(match: re.Match[str]) -> str:
        return match.group(1) + match.group(2) + match.group(3).upper()

    return _SENTENCE_RE.sub(upper, text)


def format_transcript(
    raw: str,
    *,
    voice_commands: bool = True,
    punctuation: bool = True,
) -> str:
    """Форматирует сырой текст распознавания.

    Whisper уже расставляет знаки, но мы дополнительно капитализируем
    предложения, наводим порядок в пробелах и при необходимости добавляем точку.
    """
    text = (raw or "").strip()
    if not text:
        return ""
    if voice_commands:
        text = apply_voice_commands(text)
    text = _normalize_spaces(text)
    if punctuation:
        text = _capitalize_sentences(text)
        if text and text[-1] in ",;:":
            text = text[:-1] + "."
        if text and (text[-1].isalnum() or text[-1] in "»)"):
            text += "."
    return text


def preview_text(text: str, limit: int = 70) -> str:
    one_line = " ".join((text or "").split())
    if len(one_line) <= limit:
        return one_line
    return one_line[: limit - 1].rstrip() + "…"

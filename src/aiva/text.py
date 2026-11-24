"""Text utilities for speech: sentence chunking, TTS cleanup and cheap token estimates."""

from __future__ import annotations

import re

_DEVANAGARI = re.compile("[\u0900-\u097f]")
_URL = re.compile(r"https?://\S+|www\.\S+")
_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_EMOJI = re.compile("[\U0001f300-\U0001faff\U00002600-\U000027bf\U0001f1e6-\U0001f1ff\u200d\ufe0f]+")
_MD_SYMBOLS = re.compile(r"(\*\*|__|\*|`{1,3}|^#{1,6}\s*|^\s*[-\u2022]\s+|^\s*\d+\.\s+)", flags=re.MULTILINE)
_SPACES = re.compile(r"\s+")

# A sentence ends at . ! ? । (Hindi danda) … followed by whitespace.
_SENTENCE_END = re.compile(r"([.!?।…]+[\"')\]]*)\s+")
_SOFT_BREAK = re.compile(r"([,;:—–])\s+")


def has_devanagari(text: str) -> bool:
    return bool(_DEVANAGARI.search(text))


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars/token for Latin text, ~2 for Devanagari."""
    if not text:
        return 0
    deva = len(_DEVANAGARI.findall(text))
    return int((len(text) - deva) / 4 + deva / 2) + 1


def strip_markdown(text: str) -> str:
    """Remove markdown decoration (for captions) but keep the words and emojis."""
    text = _MD_LINK.sub(r"\1", text)
    return _SPACES.sub(" ", _MD_SYMBOLS.sub("", text)).strip()


def clean_for_tts(text: str) -> str:
    """Make LLM text speakable: drop markdown, URLs and emojis; collapse whitespace."""
    text = _MD_LINK.sub(r"\1", text)
    text = _URL.sub("", text)
    text = _EMOJI.sub("", text)
    text = _MD_SYMBOLS.sub("", text)
    text = text.replace("&", " and ").replace("%", " percent") if not has_devanagari(text) else text
    return _SPACES.sub(" ", text).strip()


class SentenceChunker:
    """Turns a token stream into speakable chunks as early as possible.

    The first chunk may break at a comma once it is long enough, so the first audio
    starts sooner; later chunks break at sentence ends; anything longer than
    ``max_chars`` is split at the last soft break or space.
    """

    def __init__(self, first_min_chars: int = 28, min_chars: int = 12, max_chars: int = 220) -> None:
        self.first_min_chars = first_min_chars
        self.min_chars = min_chars
        self.max_chars = max_chars
        self._buffer = ""
        self._emitted = 0

    def feed(self, text: str) -> list[str]:
        self._buffer += text
        chunks: list[str] = []
        while True:
            chunk = self._next_chunk()
            if chunk is None:
                break
            if chunk.strip():
                chunks.append(chunk.strip())
                self._emitted += 1
        return chunks

    def flush(self) -> list[str]:
        rest, self._buffer = self._buffer.strip(), ""
        if rest:
            self._emitted += 1
            return [rest]
        return []

    def _next_chunk(self) -> str | None:
        buf = self._buffer
        min_chars = self.min_chars
        for match in _SENTENCE_END.finditer(buf):
            if match.end() >= min_chars or self._emitted == 0:
                self._buffer = buf[match.end() :]
                return buf[: match.end()]
        if self._emitted == 0 and len(buf) >= self.first_min_chars * 2:
            for match in _SOFT_BREAK.finditer(buf):
                if match.end() >= self.first_min_chars:
                    self._buffer = buf[match.end() :]
                    return buf[: match.end()]
        if len(buf) > self.max_chars:
            window = buf[: self.max_chars]
            cut = max(window.rfind(", "), window.rfind("; "), window.rfind(" "))
            cut = cut + 1 if cut > self.max_chars // 3 else self.max_chars
            self._buffer = buf[cut:]
            return buf[:cut]
        return None

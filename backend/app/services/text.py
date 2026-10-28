"""Sentence/clause boundaries and small normalisation helpers shared by the checks."""

import re
from dataclasses import dataclass

FLUFF = {
    "happy", "satisfied", "loyal", "delighted", "amazing", "our", "trusted", "real",
    "proud", "great", "wonderful", "the", "of", "all", "its", "their", "your",
}

SENTENCE_END = re.compile(r"(?<=[.!?])\s+|\n+")
# A comma counts as a clause break only when followed by a space, so "80,000" stays whole.
CLAUSE_BREAK = re.compile(r"[.!?;:\n]|,\s|\s[—–-]\s|\sand\s|\swith\s")


@dataclass
class Span:
    start: int
    end: int

    def text(self, src: str) -> str:
        return src[self.start : self.end]


def sentences(text: str) -> list[Span]:
    spans, pos = [], 0
    for m in SENTENCE_END.finditer(text):
        if m.start() > pos:
            spans.append(Span(pos, m.start()))
        pos = m.end()
    if pos < len(text):
        spans.append(Span(pos, len(text)))
    return [s for s in spans if text[s.start : s.end].strip()]


def sentence_at(text: str, index: int) -> Span:
    for s in sentences(text):
        if s.start <= index < s.end or index == s.end:
            return s
    return Span(0, len(text))


def clause_at(text: str, start: int, end: int) -> Span:
    sent = sentence_at(text, start)
    left, right = sent.start, sent.end
    for m in CLAUSE_BREAK.finditer(text, sent.start, sent.end):
        if m.end() <= start:
            left = m.end()
        elif m.start() >= end:
            right = m.start()
            break
    return Span(left, right)


def singular(word: str) -> str:
    if len(word) > 3 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def norm_words(phrase: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", phrase.lower().replace("-", " "))
    return [singular(w) for w in words if w not in FLUFF]


def norm_phrase(phrase: str) -> str:
    return " ".join(norm_words(phrase))


def find_phrase(text: str, phrase: str, start: int = 0, end: int | None = None):
    """Case-insensitive whole-word search; tolerant of hyphen/space differences."""
    words = [re.escape(w) for w in re.split(r"[\s\-]+", phrase.strip()) if w]
    if not words:
        return None
    pattern = re.compile(r"(?<![\w])" + r"[\s\-]+".join(words) + r"(?![\w])", re.IGNORECASE)
    return pattern.search(text, start, len(text) if end is None else end)

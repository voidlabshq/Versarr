from __future__ import annotations

import html
import re
import unicodedata

_LOOKUP_WHITESPACE_RE = re.compile(r"\s+")
_LYRICS_BLANK_RE = re.compile(r"\n{3,}")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_TRAILING_SPACE_RE = re.compile(r"[ \t]+\n")


def normalize_lookup_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold().strip()
    normalized = _LOOKUP_WHITESPACE_RE.sub(" ", normalized)
    return normalized


def normalize_lyrics_text(value: str) -> str:
    text = value.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    text = html.unescape(text)
    text = unicodedata.normalize("NFKC", text)
    text = _HTML_TAG_RE.sub("", text)
    text = _TRAILING_SPACE_RE.sub("\n", text)
    text = _LYRICS_BLANK_RE.sub("\n\n", text)
    return text.strip()


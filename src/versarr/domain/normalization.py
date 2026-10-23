from __future__ import annotations

import html
import re
import unicodedata

_LOOKUP_WHITESPACE_RE = re.compile(r"\s+")
_LYRICS_BLANK_RE = re.compile(r"\n{3,}")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_TRAILING_SPACE_RE = re.compile(r"[ \t]+\n")


def normalize_lookup_text(value: str) -> str:
    return _LOOKUP_WHITESPACE_RE.sub(
        " ",
        unicodedata.normalize("NFKC", value).casefold().strip(),
    )


def normalize_lyrics_text(value: str) -> str:
    """Tidy lyrics for storage: newlines, BOM, HTML, trailing space. Never rewrites characters."""
    text = value.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    text = html.unescape(text)
    text = unicodedata.normalize("NFC", text)
    return _tidy_lyrics(text)


def normalize_lyrics_for_comparison(value: str) -> str:
    """Canonical form used to decide whether two lyrics are the same text (not for writing)."""
    text = value.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    text = html.unescape(text)
    text = unicodedata.normalize("NFKC", text)
    return _tidy_lyrics(text)


def _tidy_lyrics(text: str) -> str:
    text = _HTML_TAG_RE.sub("", text)
    text = _TRAILING_SPACE_RE.sub("\n", text)
    text = _LYRICS_BLANK_RE.sub("\n\n", text)
    return text.strip()

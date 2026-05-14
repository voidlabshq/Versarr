from __future__ import annotations

from versarr.domain import normalize_lookup_text, normalize_lyrics_text


def test_lookup_normalization_casefolds_and_collapses_whitespace() -> None:
    assert normalize_lookup_text("  BeyoncÉ   Halo  ") == "beyoncé halo"


def test_lyrics_normalization_strips_html_and_blank_runs() -> None:
    source = "\ufeffHello<br>\r\n\r\n\r\nWorld &amp; Friends  \n"
    assert normalize_lyrics_text(source) == "Hello\n\nWorld & Friends"

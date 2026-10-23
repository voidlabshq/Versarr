from __future__ import annotations

from versarr.domain import hash_normalized_lyrics, normalize_lookup_text, normalize_lyrics_text


def test_lookup_normalization_casefolds_and_collapses_whitespace() -> None:
    assert normalize_lookup_text("  BeyoncÉ   Halo  ") == "beyoncé halo"


def test_lyrics_normalization_strips_html_and_blank_runs() -> None:
    source = "\ufeffHello<br>\r\n\r\n\r\nWorld &amp; Friends  \n"
    assert normalize_lyrics_text(source) == "Hello\n\nWorld & Friends"


def test_lyrics_normalization_preserves_characters() -> None:
    source = "[00:01.00]\u611b\u3057\u3066\u308b\uff01\u3000Wait\u2026 \u00bd \u2460 \ufb01ne"
    assert normalize_lyrics_text(source) == source


# Produced by the previous (NFKC-folding) writer; its provenance hash must keep matching.
_LEGACY_SIDECAR_TEXT = "[00:01.00]\u611b\u3057\u3066\u308b! Wait... 1\u20442 x 1 fine\n\n[00:05.00]Done"
_LEGACY_SIDECAR_HASH = "7087c252eb998b8f623ffdce4aaad2a340ee54cb835aad3cf698192ebfe9749d"
_PROVIDER_TEXT = "[00:01.00]\u611b\u3057\u3066\u308b\uff01\u3000Wait\u2026 \u00bd <i>x</i> \u2460 \ufb01ne\r\n\r\n\r\n\r\n[00:05.00]Done  \r\n"


def test_legacy_sidecar_still_hashes_to_its_recorded_provenance_hash() -> None:
    assert hash_normalized_lyrics(_LEGACY_SIDECAR_TEXT) == _LEGACY_SIDECAR_HASH


def test_new_and_legacy_forms_of_the_same_lyrics_hash_identically() -> None:
    assert hash_normalized_lyrics(normalize_lyrics_text(_PROVIDER_TEXT)) == _LEGACY_SIDECAR_HASH

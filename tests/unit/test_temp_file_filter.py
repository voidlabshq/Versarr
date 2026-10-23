from __future__ import annotations

from pathlib import Path

import pytest

from versarr.config.settings import ScanSettings
from versarr.infrastructure.filesystem import is_ignored_temp_file


@pytest.mark.parametrize("name", ["song.flac.part", "SONG.TMP", "x.crdownload", "a.partial", "b.download"])
def test_default_temp_patterns_are_ignored(name: str) -> None:
    assert is_ignored_temp_file(Path("/music") / name, ScanSettings().ignored_temp_patterns)


@pytest.mark.parametrize("name", ["song.flac", "song.lrc", "partial.flac"])
def test_regular_files_are_not_ignored(name: str) -> None:
    assert not is_ignored_temp_file(Path("/music") / name, ScanSettings().ignored_temp_patterns)

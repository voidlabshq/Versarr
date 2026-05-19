from __future__ import annotations

from pathlib import Path

import pytest

from versarr.config import load_settings


def test_settings_environment_overrides_toml(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    file_root = tmp_path / "from-file"
    env_root = tmp_path / "from-env"
    file_root.mkdir()
    env_root.mkdir()
    config_path = tmp_path / "versarr.toml"
    config_path.write_text(
        f"""
library_roots = ["{file_root.as_posix()}"]
provider_timeout_seconds = 10

[scan]
reconciliation_interval_seconds = 1200
stability_quiet_period_seconds = 15
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("VERSARR_LIBRARY_ROOTS", f'["{env_root.as_posix()}"]')
    monkeypatch.setenv("VERSARR_PROVIDER_TIMEOUT_SECONDS", "30")
    monkeypatch.setenv("VERSARR_SCAN__STARTUP_RECONCILIATION", "false")

    settings = load_settings(config_path)

    assert settings.library_roots == (env_root,)
    assert settings.provider_timeout_seconds == 30
    assert settings.scan.startup_reconciliation is False
    assert settings.scan.reconciliation_interval_seconds == 1200
    assert settings.scan.stability_quiet_period_seconds == 15

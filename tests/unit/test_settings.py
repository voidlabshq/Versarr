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


def test_settings_default_http_port(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VERSARR_HTTP_BIND_PORT", raising=False)
    monkeypatch.setenv("VERSARR_LIBRARY_ROOTS", f'["{tmp_path.as_posix()}"]')

    settings = load_settings()

    assert settings.http_bind_host == "0.0.0.0"
    assert settings.http_bind_port == 9280


def test_heartbeat_must_be_shorter_than_lease_ttl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VERSARR_LIBRARY_ROOTS", f'["{tmp_path.as_posix()}"]')
    monkeypatch.setenv("VERSARR_RETRY__HEARTBEAT_SECONDS", "60")
    monkeypatch.setenv("VERSARR_RETRY__LEASE_TTL_SECONDS", "60")

    with pytest.raises(ValueError, match="heartbeat_seconds must be shorter"):
        load_settings()


def test_default_user_agent_identifies_version_and_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from versarr import __version__

    monkeypatch.setenv("VERSARR_LIBRARY_ROOTS", f'["{tmp_path.as_posix()}"]')

    settings = load_settings()

    assert settings.provider_user_agent == f"Versarr/{__version__} (+https://github.com/voidlabshq/Versarr)"

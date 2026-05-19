from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict, TomlConfigSettingsSource


class RetryWindow(BaseModel):
    initial_seconds: int
    max_seconds: int
    max_attempts: int

    @model_validator(mode="after")
    def validate_window(self) -> RetryWindow:
        if self.initial_seconds <= 0 or self.max_seconds <= 0:
            msg = "retry windows must be positive"
            raise ValueError(msg)
        if self.initial_seconds > self.max_seconds:
            msg = "initial_seconds cannot exceed max_seconds"
            raise ValueError(msg)
        if self.max_attempts <= 0:
            msg = "max_attempts must be positive"
            raise ValueError(msg)
        return self


class RetrySettings(BaseModel):
    file_unstable: RetryWindow = Field(default_factory=lambda: RetryWindow(initial_seconds=5, max_seconds=600, max_attempts=8))
    provider_transient: RetryWindow = Field(default_factory=lambda: RetryWindow(initial_seconds=60, max_seconds=21600, max_attempts=5))
    heartbeat_seconds: int = 30
    lease_ttl_seconds: int = 120


class CooldownSettings(BaseModel):
    not_found_seconds: int = 7 * 24 * 60 * 60
    ambiguous_seconds: int = 3 * 24 * 60 * 60
    invalid_content_seconds: int = 3 * 24 * 60 * 60


class ScanSettings(BaseModel):
    reconciliation_interval_seconds: int = 15 * 60
    startup_reconciliation: bool = True
    stability_quiet_period_seconds: int = 15
    stability_probe_gap_seconds: int = 5
    ignored_temp_patterns: tuple[str, ...] = (
        "*.part",
        "*.tmp",
        "*.crdownload",
        "*.partial",
        "*.download",
    )


class PolicySettings(BaseModel):
    overwrite_existing: bool = False
    allow_manual_overwrite: bool = False
    preserve_embedded_only: bool = True


class Settings(BaseSettings):
    _toml_file: ClassVar[Path | None] = None

    model_config = SettingsConfigDict(
        env_prefix="VERSARR_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    config_file: Path | None = None
    library_roots: tuple[Path, ...]
    state_dir: Path = Path("/state")
    sqlite_path: Path = Path("/state/versarr.db")
    http_bind_host: str = "0.0.0.0"
    http_bind_port: int = 8080
    log_level: str = "INFO"
    worker_concurrency: int = 2
    provider_base_url: str = "https://lrclib.net"
    provider_timeout_seconds: int = 10
    provider_user_agent: str = "Versarr/0.1.0"
    scan: ScanSettings = Field(default_factory=ScanSettings)
    retry: RetrySettings = Field(default_factory=RetrySettings)
    cooldowns: CooldownSettings = Field(default_factory=CooldownSettings)
    policy: PolicySettings = Field(default_factory=PolicySettings)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            TomlConfigSettingsSource(settings_cls, toml_file=cls._toml_file),
            file_secret_settings,
        )

    @field_validator("library_roots")
    @classmethod
    def validate_library_roots(cls, value: tuple[Path, ...]) -> tuple[Path, ...]:
        if not value:
            msg = "at least one library root is required"
            raise ValueError(msg)
        resolved = tuple(path.expanduser() for path in value)
        duplicates = {path for path in resolved if resolved.count(path) > 1}
        if duplicates:
            msg = f"duplicate library roots are not allowed: {sorted(map(str, duplicates))}"
            raise ValueError(msg)
        for root in resolved:
            if not root.exists():
                msg = f"library root does not exist: {root}"
                raise ValueError(msg)
        for index, root in enumerate(resolved):
            for other in resolved[index + 1 :]:
                try:
                    resolved_root = root.resolve()
                    resolved_other = other.resolve()
                except OSError:
                    continue
                if resolved_root == resolved_other:
                    continue
                if resolved_root in resolved_other.parents or resolved_other in resolved_root.parents:
                    msg = f"overlapping library roots are not allowed: {root} and {other}"
                    raise ValueError(msg)
        return resolved

    @field_validator("worker_concurrency")
    @classmethod
    def validate_worker_concurrency(cls, value: int) -> int:
        if value <= 0:
            msg = "worker_concurrency must be positive"
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def validate_paths(self) -> Settings:
        if self.sqlite_path.parent != self.state_dir:
            msg = "sqlite_path must live under state_dir"
            raise ValueError(msg)
        return self

    def ensure_directories(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)


def load_settings(
    config_file: Path | None = None,
    overrides: dict[str, Any] | None = None,
) -> Settings:
    file_path = config_file or None
    init_values: dict[str, Any] = {}
    settings_cls = Settings
    if file_path is not None:
        init_values["config_file"] = file_path

        class ConfiguredSettings(Settings):
            _toml_file: ClassVar[Path | None] = file_path

        settings_cls = ConfiguredSettings

    if overrides:
        init_values.update(overrides)
    return settings_cls(**init_values)

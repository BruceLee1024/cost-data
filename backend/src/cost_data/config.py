from __future__ import annotations

import os
import secrets
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="COST_DATA_", extra="ignore")

    app_name: str = "工程造价数据库"
    environment: str = "development"
    data_home: Path = Path.home() / "Library" / "Application Support" / "cost-data"
    host: str = "127.0.0.1"
    port: int = 8765
    session_token: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    ai_request_timeout_seconds: int = 60
    backup_retention_daily: int = 7
    backup_retention_weekly: int = 4

    @property
    def database_dir(self) -> Path:
        return self.data_home / "database"

    @property
    def database_path(self) -> Path:
        return self.database_dir / "cost-data.sqlite3"

    @property
    def library_paths(self) -> dict[str, Path]:
        """Business-library files.  Project and import metadata stay in database_path."""
        return {
            "catalog": self.database_dir / "catalog.sqlite3",
            "resource": self.database_dir / "resource.sqlite3",
            "quota": self.database_dir / "quota.sqlite3",
        }

    @property
    def raw_dir(self) -> Path:
        return self.data_home / "raw"

    @property
    def export_dir(self) -> Path:
        return self.data_home / "exports"

    @property
    def cache_dir(self) -> Path:
        return self.data_home / "cache"

    @property
    def log_dir(self) -> Path:
        return self.data_home / "logs"

    @property
    def effective_session_token(self) -> str:
        if not self.session_token:
            self.session_token = secrets.token_urlsafe(32)
        return self.session_token

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.database_path}"

    def ensure_directories(self) -> None:
        for directory in (
            self.database_dir,
            self.raw_dir,
            self.export_dir,
            self.cache_dir,
            self.log_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    override = os.getenv("COST_DATA_HOME")
    if override:
        settings.data_home = Path(override).expanduser().resolve()
    settings.ensure_directories()
    return settings

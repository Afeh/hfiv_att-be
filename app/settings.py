from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── App ──────────────────────────────────────────────────────────
    app_title: str = "Attendance API"

    # ── Database ──────────────────────────────────────────────────────
    database_url: str  # e.g. postgresql://user:pass@host:5432/attendance

    # ── CORS ──────────────────────────────────────────────────────────
    # Comma-separated list of allowed origins (no spaces between entries).
    allowed_origins: str = "http://localhost:3000"

    # ── Auth ─────────────────────────────────────────────────────────
    # PIN to access the app. Override via APP_PIN env var.
    app_pin: str

    # ── Runtime ───────────────────────────────────────────────────────
    debug: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"


settings = Settings()  # singleton – import this in other modules

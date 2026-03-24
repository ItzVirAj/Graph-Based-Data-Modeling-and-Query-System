from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"

if ENV_PATH.exists():
    load_dotenv(ENV_PATH, override=False)


def _split_csv(value: str | None, default: list[str]) -> list[str]:
    if value is None:
        return default
    items = [item.strip() for item in value.split(",")]
    return [item for item in items if item]


class Settings:
    app_env: str
    api_host: str
    api_port: int
    log_level: str
    allowed_origins: list[str]
    data_dir: Path

    def __init__(self) -> None:
        self.app_env = os.getenv("APP_ENV", "development").strip().lower()
        self.api_host = os.getenv("API_HOST", "0.0.0.0").strip()
        self.api_port = int(os.getenv("API_PORT", "8000"))
        self.log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper()
        self.allowed_origins = _split_csv(
            os.getenv("ALLOWED_ORIGINS"),
            default=["http://localhost:5173", "http://127.0.0.1:5173"],
        )
        self.data_dir = Path(os.getenv("DATA_DIR", PROJECT_ROOT / "sap-o2c-data")).resolve()


settings = Settings()

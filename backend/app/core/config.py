"""Application configuration. All secrets come from environment variables (see .env.example)."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", str(ROOT / ".env")), extra="ignore")

    app_name: str = "DISHA"
    environment: str = "development"
    # sqlite keeps the project runnable without Docker; use postgresql+psycopg://... (PostGIS) in production
    database_url: str = f"sqlite:///{(ROOT / 'data' / 'disha.db').as_posix()}"
    redis_url: str | None = None
    data_dir: Path = ROOT / "data"
    models_dir: Path = ROOT / "models"

    jwt_secret: str = "change-me-in-production-this-is-a-dev-default-only"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 720
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    h3_resolution: int = 8  # ~460 m edge, ~0.74 km2; configurable per event
    demo_mode: bool = True
    demo_step_delay: float = 1.6  # seconds between pipeline stages in demo pacing
    seed_demo_accounts: bool = True
    demo_password: str = "Disha@2026"  # DEMO ONLY - printed on the login page

    # Notification providers: "mock" logs to the Notification table. Real providers read keys from env.
    notify_provider: str = "mock"
    smtp_url: str | None = None
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None

    # Live-data hooks (not used in demo mode)
    cdse_username: str | None = None
    cdse_password: str | None = None

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.data_dir.mkdir(parents=True, exist_ok=True)
    s.models_dir.mkdir(parents=True, exist_ok=True)
    return s

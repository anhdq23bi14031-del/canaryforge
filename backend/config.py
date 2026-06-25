from pydantic_settings import BaseSettings
from typing import List
import secrets


class Settings(BaseSettings):
    # Core
    SECRET_KEY: str = secrets.token_hex(32)
    BASE_URL: str = "http://localhost:8000"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./canaryforge.db"

    def model_post_init(self, __context) -> None:
        # Railway (and most providers) hand out DATABASE_URL as
        # postgresql:// or postgres://, which psycopg-style drivers expect.
        # Our async setup needs the asyncpg dialect explicitly.
        if self.DATABASE_URL.startswith("postgres://"):
            self.DATABASE_URL = self.DATABASE_URL.replace(
                "postgres://", "postgresql+asyncpg://", 1
            )
        elif self.DATABASE_URL.startswith("postgresql://"):
            self.DATABASE_URL = self.DATABASE_URL.replace(
                "postgresql://", "postgresql+asyncpg://", 1
            )

    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173"]

    # Anthropic (for LLM-generated decoy content)
    ANTHROPIC_API_KEY: str = ""

    # Alerting
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    ALERT_FROM_EMAIL: str = "canaryforge@localhost"
    ALERT_TO_EMAIL: str = ""

    SLACK_WEBHOOK_URL: str = ""

    # Scoring thresholds
    ALERT_SCORE_THRESHOLD: int = 40  # Min score to fire an alert
    FALSE_POSITIVE_SCORE: int = 10   # Max score before considered FP

    # IPs/CIDR ranges that should NEVER trigger an alert (your own office,
    # security team, monitoring tools, etc). Comma-separated in .env.
    ALLOWLISTED_IPS: List[str] = []

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
"""Application settings loaded from the environment and an optional .env file."""

from __future__ import annotations

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Runtime configuration. Secrets come only from the environment."""

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://geopolitics:geopolitics@localhost:5432/geopolitics"
    cors_origins: str = "http://localhost:5173"
    newsapi_key: str = ""
    gnews_api_key: str = ""
    guardian_api_key: str = ""
    admin_api_key: str = "change-me"
    ingest_interval_minutes: int = 30
    process_batch_size: int = 20
    # BART-family primary (DistilBART). T5 is the second neural summariser.
    summary_model: str = "sshleifer/distilbart-cnn-12-6"
    summary_model_t5: str = "t5-small"
    sentiment_model: str = "cardiffnlp/twitter-roberta-base-sentiment-latest"
    ner_model: str = "dslim/bert-base-NER"
    enable_scheduler: bool = False
    hf_home: str = "./.hf_cache"
    classifier_path: str = "ml/artifacts/classifier.joblib"

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        """Accept Render/Heroku-style URLs and force the psycopg v3 driver."""
        if not isinstance(value, str):
            return value
        if value.startswith("postgres://"):
            return "postgresql+psycopg://" + value[len("postgres://") :]
        if value.startswith("postgresql://"):
            return "postgresql+psycopg://" + value[len("postgresql://") :]
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()

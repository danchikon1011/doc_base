"""Application configuration using Pydantic settings."""
from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import BaseSettings, Field


class Settings(BaseSettings):
    """Central application settings loaded from environment variables."""

    project_name: str = Field(default="DocuFlow")
    backend_cors_origins: List[str] = Field(default_factory=lambda: ["*"])

    postgres_user: str = Field(default="docflow")
    postgres_password: str = Field(default="docflow")
    postgres_host: str = Field(default="db")
    postgres_port: int = Field(default=5432)
    postgres_db: str = Field(default="docflow")

    secret_key: str = Field(default="super-secret-change-me")
    access_token_expire_minutes: int = Field(default=60 * 24)

    file_storage_path: Path = Field(default=Path("storage"))

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @property
    def sqlalchemy_database_uri(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"\
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.file_storage_path.mkdir(parents=True, exist_ok=True)
    return settings

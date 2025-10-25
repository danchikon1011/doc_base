import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def get_database_path() -> str:
    default_path = BASE_DIR / "instance" / "docbase.db"
    return os.getenv("DOCBASE_DATABASE_PATH", str(default_path))


class Config:
    SECRET_KEY = os.getenv("DOCBASE_SECRET_KEY", "change-me")
    DATABASE_PATH = get_database_path()
    UPLOAD_FOLDER = os.getenv("DOCBASE_UPLOAD_FOLDER", str(BASE_DIR / "storage"))
    MAX_CONTENT_LENGTH = 32 * 1024 * 1024  # 32MB
    SECURITY_PASSWORD_SALT = os.getenv("DOCBASE_PASSWORD_SALT", "docbase-salt")


class TestingConfig(Config):
    TESTING = True
    DATABASE_PATH = os.getenv("DOCBASE_TEST_DATABASE", ":memory:")

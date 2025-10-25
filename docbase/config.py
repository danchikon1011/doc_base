import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def get_database_uri() -> str:
    default_path = BASE_DIR / "instance" / "docbase.db"
    return os.getenv("DOCBASE_DATABASE_URI", f"sqlite:///{default_path}")


class Config:
    SECRET_KEY = os.getenv("DOCBASE_SECRET_KEY", "change-me")
    SQLALCHEMY_DATABASE_URI = get_database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.getenv("DOCBASE_UPLOAD_FOLDER", str(BASE_DIR / "storage"))
    MAX_CONTENT_LENGTH = 32 * 1024 * 1024  # 32MB
    SECURITY_PASSWORD_SALT = os.getenv("DOCBASE_PASSWORD_SALT", "docbase-salt")


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"

"""Database session and engine helpers."""
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .config import get_settings

settings = get_settings()

engine = create_engine(settings.sqlalchemy_database_uri, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@contextmanager
def get_db():
    """Yield a database session that is closed afterwards."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

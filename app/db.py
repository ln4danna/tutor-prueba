"""Engine de SQLAlchemy y sesión por request."""
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.models import Base

# check_same_thread=False: FastAPI puede atender un request en otro hilo que el que abrió la conexión.
engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def get_db() -> Iterator[Session]:
    """Dependencia de FastAPI: una sesión por request, siempre cerrada."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
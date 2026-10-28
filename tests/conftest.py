"""Fixtures compartidos: base SQLite en memoria con el seed, sin internet ni API key."""
import os

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ["DATABASE_URL"] = "sqlite://"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import get_db
from app.main import app
from app.models import Base, User
from seed import DEMO_PASSWORD, seed


@pytest.fixture
def db_session():
    # StaticPool: todas las conexiones comparten la misma base en memoria.
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, expire_on_commit=False)
    with TestSession() as session:
        seed(session)
    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestSession() as session:
        yield session
    app.dependency_overrides.clear()


@pytest.fixture
def client(db_session: Session) -> TestClient:
    return TestClient(app)


def login(client: TestClient, email: str) -> None:
    r = client.post(
        "/login", data={"email": email, "password": DEMO_PASSWORD}, follow_redirects=False
    )
    assert r.status_code == 303


def user_id(db: Session, email: str) -> int:
    return db.scalar(select(User.id).where(User.email == email))

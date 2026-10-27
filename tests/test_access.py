"""Acceso: sin sesión, con acceso, sin acceso e IDOR."""
import time

import pytest
from itsdangerous import TimestampSigner, URLSafeTimedSerializer
from sqlalchemy import select

from app.config import settings
from app.models import Course, Enrollment, Message
from tests.conftest import login, user_id

PROTECTED = ["/courses", "/lessons/1", "/lessons/1/messages"]


@pytest.mark.parametrize("path", PROTECTED)
def test_without_session_returns_401(client, path):
    assert client.get(path).status_code == 401


def test_without_session_browser_is_redirected_to_login(client):
    r = client.get("/courses", headers={"accept": "text/html"}, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


def test_tampered_cookie_returns_401(client):
    client.cookies.set("session", "falsificada")
    assert client.get("/courses").status_code == 401


class _OldSigner(TimestampSigner):
    """Firma con fecha en el pasado para simular una cookie copiada que ya venció."""

    def get_timestamp(self) -> int:
        return int(time.time()) - settings.session_max_age_seconds - 60


def test_expired_cookie_is_rejected_by_server(client, db_session):
    # Firma válida pero vieja: el servidor valida la antigüedad, no solo el navegador.
    serializer = URLSafeTimedSerializer(settings.secret_key, salt="session", signer=_OldSigner)
    token = serializer.dumps({"uid": user_id(db_session, "ana@demo.com")})
    client.cookies.set("session", token)
    assert client.get("/courses").status_code == 401


def test_valid_cookie_for_missing_user_returns_401(client):
    token = URLSafeTimedSerializer(settings.secret_key, salt="session").dumps({"uid": 9999})
    client.cookies.set("session", token)
    assert client.get("/courses").status_code == 401


def test_login_sets_secure_cookie_flags(client):
    r = client.post(
        "/login", data={"email": "ana@demo.com", "password": "demo1234"}, follow_redirects=False
    )
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "max-age" in cookie


@pytest.mark.parametrize(
    "email,password", [("ana@demo.com", "incorrecta"), ("noexiste@demo.com", "demo1234")]
)
def test_login_failure_uses_generic_message(client, email, password):
    r = client.post("/login", data={"email": email, "password": password})
    assert r.status_code == 401
    assert r.json()["detail"] == "Email o contraseña incorrectos."


def test_enrolled_user_sees_course_and_lesson(client):
    login(client, "ana@demo.com")
    courses = client.get("/courses").json()
    assert [c["title"] for c in courses] == ["Introducción a las APIs REST"]
    r = client.get("/lessons/1")
    assert r.status_code == 200
    assert "POST" in r.json()["content"]


def test_unenrolled_user_gets_403(client):
    login(client, "beto@demo.com")
    assert client.get("/courses").json() == []
    assert client.get("/lessons/1").status_code == 403
    assert client.get("/lessons/1/messages").status_code == 403


def test_unknown_lesson_returns_404(client):
    login(client, "ana@demo.com")
    assert client.get("/lessons/999").status_code == 404


def test_idor_user_cannot_read_other_users_messages(client, db_session):
    ana, beto = user_id(db_session, "ana@demo.com"), user_id(db_session, "beto@demo.com")
    course_id = db_session.scalar(select(Course.id))
    # Beto también se inscribe: así el único control que queda es el filtro por user_id.
    db_session.add(Enrollment(user_id=beto, course_id=course_id))
    db_session.add(Message(user_id=ana, lesson_id=1, role="user", content="secreto de ana"))
    db_session.commit()

    login(client, "beto@demo.com")
    assert client.get("/lessons/1/messages").json() == []
    # Intentar forzar el id de Ana por query no tiene efecto: el endpoint ignora el parámetro.
    assert client.get(f"/lessons/1/messages?user_id={ana}").json() == []
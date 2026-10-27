"""Login, logout, cookie de sesión firmada y dependencia get_current_user."""
import bcrypt
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import User
from app.templating import templates

LOGIN_ERROR = "Email o contraseña incorrectos."

SESSION_COOKIE = "session"
_serializer = URLSafeTimedSerializer(settings.secret_key, salt="session")

# Hash ficticio: si el email no existe igual se ejecuta bcrypt, para que el tiempo
# de respuesta no revele qué cuentas existen.
_DUMMY_HASH = bcrypt.hashpw(b"dummy-password", bcrypt.gensalt()).decode()

router = APIRouter()


class NotAuthenticated(Exception):
    """Se traduce a 401 (API) o redirección a /login (navegador) en main.py."""


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def authenticate(db: Session, email: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None:
        verify_password(password, _DUMMY_HASH)
        return None
    return user if verify_password(password, user.password_hash) else None


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Único origen del usuario actual: la cookie firmada. Nunca un id del request."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise NotAuthenticated()
    try:
        data = _serializer.loads(token, max_age=settings.session_max_age_seconds)
    except (BadSignature, SignatureExpired):
        raise NotAuthenticated() from None
    user = db.get(User, data.get("uid"))
    if user is None:
        raise NotAuthenticated()
    return user


@router.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {})


@router.post("/login")
def login(
    request: Request,
    email: str = Form(..., max_length=255),
    password: str = Form(..., max_length=255),
    db: Session = Depends(get_db),
):
    user = authenticate(db, email, password)
    if user is None:
        # Mismo mensaje para email inexistente o contraseña incorrecta.
        return templates.TemplateResponse(
            request, "login.html", {"error": LOGIN_ERROR, "email": email}, status_code=401
        )
    # Destino fijo (sin parámetro `next`): evita open redirects.
    response = RedirectResponse("/courses", status_code=303)
    response.set_cookie(
        SESSION_COOKIE,
        _serializer.dumps({"uid": user.id}),
        max_age=settings.session_max_age_seconds,
        httponly=True,  # JS no puede leerla: un XSS no roba la sesión.
        samesite="lax",  # Mitigación básica de CSRF.
        secure=settings.cookie_secure,
    )
    return response


@router.post("/logout")
def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response
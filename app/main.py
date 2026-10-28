"""Crea la app FastAPI y monta las rutas."""
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import auth
from app.db import init_db
from app.routes import chat, lessons
from app.templating import templates

SECURITY_HEADERS = {
    # Solo recursos propios: aunque se colara HTML, un script inline o externo no se ejecutaría.
    "Content-Security-Policy": (
        "default-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'self'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
}


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    init_db()
    yield


app = FastAPI(title="Tutor POC", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
app.include_router(auth.router)
app.include_router(lessons.router)
app.include_router(chat.router)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.update(SECURITY_HEADERS)
    return response


def wants_html(request: Request) -> bool:
    """Navegador pidiendo una página (Accept: text/html) vs. fetch/API."""
    return "text/html" in request.headers.get("accept", "")


@app.get("/", include_in_schema=False)
def index():
    return RedirectResponse("/courses", status_code=303)


@app.exception_handler(auth.NotAuthenticated)
async def not_authenticated_handler(request: Request, _: auth.NotAuthenticated):
    if wants_html(request):
        return RedirectResponse("/login", status_code=303)
    return JSONResponse({"detail": "No autenticado."}, status_code=401)


@app.exception_handler(StarletteHTTPException)
async def html_error_handler(request: Request, exc: StarletteHTTPException):
    # Mismo criterio que el 401: página legible para el navegador, JSON para la API.
    if wants_html(request):
        return templates.TemplateResponse(
            request,
            "error.html",
            {"status_code": exc.status_code, "message": exc.detail},
            status_code=exc.status_code,
        )
    return await http_exception_handler(request, exc)
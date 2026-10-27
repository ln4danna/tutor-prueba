"""Crea la app FastAPI y monta las rutas."""
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse

from app import auth
from app.db import init_db
from app.routes import chat, lessons


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    init_db()
    yield


app = FastAPI(title="Tutor POC", lifespan=lifespan)
app.include_router(auth.router)
app.include_router(lessons.router)
app.include_router(chat.router)


@app.exception_handler(auth.NotAuthenticated)
async def not_authenticated_handler(request: Request, _: auth.NotAuthenticated):
    # Un navegador pidiendo una página va al login; fetch/API recibe 401.
    if "text/html" in request.headers.get("accept", ""):
        return RedirectResponse("/login", status_code=303)
    return JSONResponse({"detail": "No autenticado."}, status_code=401)
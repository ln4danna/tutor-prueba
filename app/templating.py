"""Instancia compartida de Jinja2 (autoescape activo para .html por defecto)."""
from pathlib import Path

from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

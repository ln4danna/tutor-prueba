"""Lee la configuración desde variables de entorno (.env en desarrollo)."""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    database_url: str
    secret_key: str
    session_max_age_seconds: int
    cookie_secure: bool
    ai_api_key: str
    ai_model: str
    ai_timeout_seconds: float


def get_settings() -> Settings:
    secret_key = os.getenv("SECRET_KEY", "")
    # Sin valor por defecto: una clave conocida permitiría falsificar cookies de sesión.
    if not secret_key:
        raise RuntimeError("Falta SECRET_KEY. Copia .env.example a .env y define un valor aleatorio.")
    return Settings(
        database_url=os.getenv("DATABASE_URL", "sqlite:///./tutor.db"),
        secret_key=secret_key,
        session_max_age_seconds=int(os.getenv("SESSION_MAX_AGE_SECONDS", str(8 * 3600))),
        # En localhost sin HTTPS una cookie Secure no se enviaría; en producción debe ser true.
        cookie_secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
        ai_api_key=os.getenv("AI_API_KEY", "").strip(),
        # Sin valor por defecto: los nombres de modelo cambian; se define en .env.
        ai_model=os.getenv("AI_MODEL", "").strip(),
        ai_timeout_seconds=float(os.getenv("AI_TIMEOUT_SECONDS", "30")),
    )


settings = get_settings()
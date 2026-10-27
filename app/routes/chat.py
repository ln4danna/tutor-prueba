"""Historial y chat de una lección."""
import logging
from datetime import UTC
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import ai
from app.auth import get_current_user
from app.db import get_db
from app.models import Lesson, Message, User
from app.permissions import get_accessible_lesson

logger = logging.getLogger(__name__)

router = APIRouter()

HISTORY_LIMIT = 6  # últimos mensajes que se envían a la IA como contexto
MAX_QUESTION_LENGTH = 1000


class ChatRequest(BaseModel):
    # Solo se declaran estos campos: cualquier otro (p. ej. un user_id) se ignora.
    question: str = Field(min_length=1, max_length=MAX_QUESTION_LENGTH)
    input_mode: Literal["text", "voice"] = "text"

    @field_validator("question", mode="before")
    @classmethod
    def strip_question(cls, value):
        # Antes de validar el largo: así "   " cuenta como vacío.
        return value.strip() if isinstance(value, str) else value


def serialize(message: Message) -> dict:
    created_at = message.created_at
    if created_at.tzinfo is None:  # SQLite devuelve fechas sin zona: se guardaron en UTC
        created_at = created_at.replace(tzinfo=UTC)
    return {
        "id": message.id,
        "role": message.role,
        "content": message.content,
        "input_mode": message.input_mode,
        "created_at": created_at.isoformat(),
    }


def conversation_query(user_id: int, lesson_id: int):
    # Siempre filtra por el user_id de la sesión y la lección: nunca mensajes ajenos.
    return select(Message).where(Message.user_id == user_id, Message.lesson_id == lesson_id)


@router.get("/lessons/{lesson_id}/messages")
def list_messages(
    lesson: Lesson = Depends(get_accessible_lesson),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    messages = db.scalars(
        conversation_query(user.id, lesson.id).order_by(Message.created_at, Message.id)
    ).all()
    return [serialize(m) for m in messages]


@router.delete("/lessons/{lesson_id}/messages", status_code=204)
def delete_messages(
    lesson: Lesson = Depends(get_accessible_lesson),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Borra SOLO los mensajes del usuario de sesión en esta lección (hard delete).

    Los permisos (401 sin sesión, 403 sin inscripción, 404 sin lección) los
    gestiona get_accessible_lesson; no se duplica esa lógica aquí.
    """
    db.execute(delete(Message).where(Message.user_id == user.id, Message.lesson_id == lesson.id))
    db.commit()
    return Response(status_code=204)


@router.post("/lessons/{lesson_id}/chat")
def chat(
    payload: ChatRequest,
    lesson: Lesson = Depends(get_accessible_lesson),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # El permiso (get_accessible_lesson) ya se evaluó: un alumno sin acceso nunca llega a la IA.
    recent = db.scalars(
        conversation_query(user.id, lesson.id)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(HISTORY_LIMIT)
    ).all()
    history = [(m.role, m.content) for m in reversed(recent)]

    try:
        answer = ai.ask_tutor(lesson.content, history, payload.question)
    except ai.AIServiceError as exc:
        # No se guarda nada: el cliente conserva la pregunta y puede reintentar sin duplicados.
        logger.warning("Chat sin respuesta (user=%s, lesson=%s): %s", user.id, lesson.id, exc)
        raise HTTPException(status_code=502, detail=exc.user_message) from exc

    # Pregunta y respuesta se guardan juntas, en una sola transacción, solo si la IA respondió.
    question_msg = Message(
        user_id=user.id,
        lesson_id=lesson.id,
        role="user",
        content=payload.question,
        input_mode=payload.input_mode,
    )
    answer_msg = Message(user_id=user.id, lesson_id=lesson.id, role="assistant", content=answer)
    db.add_all([question_msg, answer_msg])
    db.commit()
    return {"question": serialize(question_msg), "answer": serialize(answer_msg)}

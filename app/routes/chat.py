"""Historial y chat de una lección. El POST /chat se agrega en la Fase 4."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_db
from app.models import Lesson, Message, User
from app.permissions import get_accessible_lesson

router = APIRouter()


@router.get("/lessons/{lesson_id}/messages")
def list_messages(
    lesson: Lesson = Depends(get_accessible_lesson),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Filtro por user_id de la sesión: aunque se manipulen ids, nunca se ven mensajes ajenos.
    messages = db.scalars(
        select(Message)
        .where(Message.lesson_id == lesson.id, Message.user_id == user.id)
        .order_by(Message.created_at, Message.id)
    ).all()
    return [
        {
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "input_mode": m.input_mode,
            "created_at": m.created_at.isoformat(),
        }
        for m in messages
    ]

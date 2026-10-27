"""Dependencia única de permisos sobre lecciones."""
from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_db
from app.models import Enrollment, Lesson, User


def get_accessible_lesson(
    lesson_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Lesson:
    """Carga la lección y exige que el usuario esté inscrito en su curso.

    Todos los endpoints de lección dependen de esta función, así la regla vive en un solo lugar.
    """
    lesson = db.get(Lesson, lesson_id)
    if lesson is None:
        raise HTTPException(status_code=404, detail="Lección no encontrada.")
    enrolled = db.scalar(
        select(Enrollment.id).where(
            Enrollment.user_id == user.id, Enrollment.course_id == lesson.course_id
        )
    )
    if enrolled is None:
        # 403 es explícito; 404 ocultaría que la lección existe (ver README).
        raise HTTPException(status_code=403, detail="No tienes acceso a esta lección.")
    return lesson
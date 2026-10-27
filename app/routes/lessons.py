"""Páginas de cursos y lecciones."""
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_db
from app.models import Course, Enrollment, Lesson, User
from app.permissions import get_accessible_lesson
from app.templating import templates

router = APIRouter()


@router.get("/courses")
def list_courses(
    request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    # El join con Enrollment filtra por el usuario de la sesión: solo cursos inscritos.
    courses = db.scalars(
        select(Course).join(Enrollment).where(Enrollment.user_id == user.id).order_by(Course.id)
    ).all()
    return templates.TemplateResponse(request, "courses.html", {"user": user, "courses": courses})


@router.get("/lessons/{lesson_id}")
def get_lesson(
    request: Request,
    lesson: Lesson = Depends(get_accessible_lesson),
    user: User = Depends(get_current_user),
):
    return templates.TemplateResponse(request, "lesson.html", {"user": user, "lesson": lesson})

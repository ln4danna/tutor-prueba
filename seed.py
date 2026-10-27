"""Datos de prueba: 1 curso, 2 lecciones, 2 alumnos. Idempotente."""
import bcrypt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal, init_db
from app.models import Course, Enrollment, Lesson, User

DEMO_PASSWORD = "demo1234"  # Solo para la demo; documentada en el README.

LESSON_1 = """Una API (Application Programming Interface) es un conjunto de reglas que permite \
que dos programas se comuniquen. En una API REST, el cliente envía peticiones HTTP a un servidor \
para trabajar con recursos identificados por URLs (por ejemplo /usuarios/5).

Métodos HTTP principales:
- GET: obtiene o lee un recurso sin modificarlo. Ejemplo: GET /usuarios/5 devuelve los datos del usuario 5.
- POST: crea un recurso nuevo enviando datos en el cuerpo de la petición. Ejemplo: POST /usuarios \
con un nombre y un email crea un usuario nuevo. También se usa para enviar datos que el servidor \
debe procesar, como un formulario.
- PUT: reemplaza o actualiza un recurso existente. Ejemplo: PUT /usuarios/5 actualiza al usuario 5.
- DELETE: elimina un recurso. Ejemplo: DELETE /usuarios/5 borra al usuario 5.

GET y DELETE no suelen llevar cuerpo; POST y PUT normalmente envían datos en JSON."""

LESSON_2 = """Cada respuesta HTTP incluye un código de estado que indica el resultado de la petición:
- 2xx éxito: 200 OK (todo bien), 201 Created (recurso creado, típico tras un POST), 204 No Content.
- 4xx error del cliente: 400 Bad Request (datos inválidos), 401 Unauthorized (falta autenticación), \
403 Forbidden (autenticado pero sin permiso), 404 Not Found (el recurso no existe).
- 5xx error del servidor: 500 Internal Server Error, 503 Service Unavailable.

JSON (JavaScript Object Notation) es el formato más usado para intercambiar datos en APIs REST. \
Usa pares clave-valor entre llaves, por ejemplo {"nombre": "Ana", "edad": 30}. Admite textos, \
números, booleanos (true/false), null, listas [ ] y objetos anidados. La cabecera \
Content-Type: application/json indica que el cuerpo está en JSON."""


def get_or_create_user(db: Session, email: str, name: str) -> User:
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        hashed = bcrypt.hashpw(DEMO_PASSWORD.encode(), bcrypt.gensalt()).decode()
        user = User(email=email, name=name, password_hash=hashed)
        db.add(user)
        db.flush()
    return user


def get_or_create_course(db: Session) -> Course:
    title = "Introducción a las APIs REST"
    course = db.scalar(select(Course).where(Course.title == title))
    if course is None:
        course = Course(title=title, description="Conceptos básicos para consumir y entender APIs REST.")
        db.add(course)
        db.flush()
    return course


def ensure_lesson(db: Session, course: Course, position: int, title: str, content: str) -> None:
    exists = db.scalar(
        select(Lesson).where(Lesson.course_id == course.id, Lesson.position == position)
    )
    if exists is None:
        db.add(Lesson(course_id=course.id, position=position, title=title, content=content))


def ensure_enrollment(db: Session, user: User, course: Course) -> None:
    exists = db.scalar(
        select(Enrollment).where(Enrollment.user_id == user.id, Enrollment.course_id == course.id)
    )
    if exists is None:
        db.add(Enrollment(user_id=user.id, course_id=course.id))


def seed(db: Session) -> None:
    course = get_or_create_course(db)
    ensure_lesson(db, course, 1, "Qué es una API y los métodos HTTP", LESSON_1)
    ensure_lesson(db, course, 2, "Códigos de estado HTTP y JSON", LESSON_2)
    ana = get_or_create_user(db, "ana@demo.com", "Ana")
    get_or_create_user(db, "beto@demo.com", "Beto")  # sin inscripción, a propósito
    ensure_enrollment(db, ana, course)
    db.commit()


if __name__ == "__main__":
    init_db()
    with SessionLocal() as session:
        seed(session)
    print("Seed listo. Usuarios: ana@demo.com (con acceso), beto@demo.com (sin acceso).")
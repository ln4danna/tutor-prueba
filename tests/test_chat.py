"""Chat: permisos antes de la IA, guardado atómico, historial y errores (IA simulada)."""
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app import ai
from app.models import Enrollment, Message
from tests.conftest import login, user_id

CHAT_URL = "/lessons/1/chat"


class FakeAI:
    """Reemplaza ai.ask_tutor: registra las llamadas y responde o falla a pedido."""

    def __init__(self):
        self.calls: list[tuple[str, list[tuple[str, str]], str]] = []
        self.answer = "POST sirve para crear recursos nuevos."
        self.error: Exception | None = None

    def __call__(self, lesson_content, history, question):
        self.calls.append((lesson_content, history, question))
        if self.error:
            raise self.error
        return self.answer


@pytest.fixture
def fake_ai(monkeypatch):
    fake = FakeAI()
    monkeypatch.setattr(ai, "ask_tutor", fake)
    return fake


def count_messages(db) -> int:
    return db.scalar(select(func.count()).select_from(Message))


def test_chat_without_session_returns_401(client, fake_ai):
    assert client.post(CHAT_URL, json={"question": "hola"}).status_code == 401
    assert fake_ai.calls == []


def test_unenrolled_user_gets_403_and_ai_is_not_called(client, fake_ai, db_session):
    login(client, "beto@demo.com")
    r = client.post(CHAT_URL, json={"question": "¿Para qué sirve POST?"})
    assert r.status_code == 403
    assert fake_ai.calls == []  # el permiso se evalúa antes de gastar una llamada a la IA
    assert count_messages(db_session) == 0


def test_chat_saves_question_and_answer(client, fake_ai, db_session):
    login(client, "ana@demo.com")
    r = client.post(CHAT_URL, json={"question": "¿Para qué sirve POST?", "input_mode": "voice"})
    assert r.status_code == 200
    assert r.json()["answer"]["content"] == fake_ai.answer

    ana = user_id(db_session, "ana@demo.com")
    saved = db_session.scalars(select(Message).order_by(Message.id)).all()
    assert [(m.user_id, m.lesson_id, m.role, m.content, m.input_mode) for m in saved] == [
        (ana, 1, "user", "¿Para qué sirve POST?", "voice"),
        (ana, 1, "assistant", fake_ai.answer, "text"),
    ]
    # La IA recibió el contenido de la lección desde la base, no desde el cliente.
    assert "POST" in fake_ai.calls[0][0]


def test_ai_failure_returns_controlled_error_and_saves_nothing(client, fake_ai, db_session):
    fake_ai.error = ai.AIServiceError("El tutor tardó demasiado en responder. Inténtalo de nuevo.")
    login(client, "ana@demo.com")
    r = client.post(CHAT_URL, json={"question": "¿Para qué sirve POST?"})
    assert r.status_code == 502
    assert r.json() == {"detail": "El tutor tardó demasiado en responder. Inténtalo de nuevo."}
    assert count_messages(db_session) == 0


def test_retry_after_failure_does_not_duplicate_question(client, fake_ai, db_session):
    login(client, "ana@demo.com")
    fake_ai.error = ai.AIServiceError("falló")
    assert client.post(CHAT_URL, json={"question": "¿Qué es GET?"}).status_code == 502
    fake_ai.error = None
    assert client.post(CHAT_URL, json={"question": "¿Qué es GET?"}).status_code == 200
    roles = db_session.scalars(select(Message.role).order_by(Message.id)).all()
    assert roles == ["user", "assistant"]


@pytest.mark.parametrize("question", ["", "   ", "\n\t ", "x" * 1001])
def test_invalid_question_is_rejected_with_422(client, fake_ai, db_session, question):
    login(client, "ana@demo.com")
    assert client.post(CHAT_URL, json={"question": question}).status_code == 422
    assert fake_ai.calls == []
    assert count_messages(db_session) == 0


def test_question_at_max_length_is_accepted(client, fake_ai):
    login(client, "ana@demo.com")
    assert client.post(CHAT_URL, json={"question": "x" * 1000}).status_code == 200


def test_invalid_input_mode_and_missing_question_are_rejected(client, fake_ai):
    login(client, "ana@demo.com")
    assert client.post(CHAT_URL, json={"question": "hola", "input_mode": "video"}).status_code == 422
    assert client.post(CHAT_URL, json={}).status_code == 422


def test_user_id_in_body_is_ignored(client, fake_ai, db_session):
    ana, beto = user_id(db_session, "ana@demo.com"), user_id(db_session, "beto@demo.com")
    login(client, "ana@demo.com")
    r = client.post(CHAT_URL, json={"question": "hola", "user_id": beto})
    assert r.status_code == 200
    owners = set(db_session.scalars(select(Message.user_id)).all())
    assert owners == {ana}


def test_history_sent_to_ai_is_limited_chronological_and_only_own(client, fake_ai, db_session):
    ana, beto = user_id(db_session, "ana@demo.com"), user_id(db_session, "beto@demo.com")
    db_session.add(Enrollment(user_id=beto, course_id=1))
    start = datetime(2026, 1, 1, tzinfo=UTC)
    for i in range(10):
        db_session.add(
            Message(
                user_id=ana,
                lesson_id=1,
                role="user" if i % 2 == 0 else "assistant",
                content=f"m{i}",
                created_at=start + timedelta(minutes=i),
            )
        )
    db_session.add(Message(user_id=beto, lesson_id=1, role="user", content="de beto", created_at=start))
    db_session.commit()

    login(client, "ana@demo.com")
    client.post(CHAT_URL, json={"question": "nueva"})
    history = fake_ai.calls[0][1]
    assert history == [
        ("user", "m4"),
        ("assistant", "m5"),
        ("user", "m6"),
        ("assistant", "m7"),
        ("user", "m8"),
        ("assistant", "m9"),
    ]


def test_messages_endpoint_returns_only_own_in_order(client, fake_ai, db_session):
    login(client, "ana@demo.com")
    client.post(CHAT_URL, json={"question": "primera"})
    client.post(CHAT_URL, json={"question": "segunda"})
    other = user_id(db_session, "beto@demo.com")
    db_session.add(Enrollment(user_id=other, course_id=1))
    db_session.add(Message(user_id=other, lesson_id=1, role="user", content="ajeno"))
    db_session.commit()

    messages = client.get("/lessons/1/messages").json()
    assert [(m["role"], m["content"]) for m in messages] == [
        ("user", "primera"),
        ("assistant", fake_ai.answer),
        ("user", "segunda"),
        ("assistant", fake_ai.answer),
    ]
    assert messages[0]["created_at"].endswith("+00:00")  # UTC explícito para el frontend


# ---------------------------------------------------------------------------
# DELETE /lessons/{lesson_id}/messages
# ---------------------------------------------------------------------------

DELETE_URL = "/lessons/1/messages"


def _seed_messages(db_session, user_email: str, lesson_id: int, count: int = 2) -> None:
    """Inserta `count` mensajes de usuario para un alumno ya inscrito."""
    uid = user_id(db_session, user_email)
    for i in range(count):
        db_session.add(
            Message(user_id=uid, lesson_id=lesson_id, role="user", content=f"msg{i}")
        )
    db_session.commit()


def test_delete_conversation_returns_204_and_clears_history(client, fake_ai, db_session):
    """Ana borra su conversación: 204 y el historial queda vacío."""
    login(client, "ana@demo.com")
    client.post(CHAT_URL, json={"question": "hola"})
    assert count_messages(db_session) == 2  # pregunta + respuesta

    r = client.delete(DELETE_URL)
    assert r.status_code == 204
    assert count_messages(db_session) == 0


def test_delete_does_not_affect_other_user_messages(client, fake_ai, db_session):
    """Borrar la conversación de ana no toca los mensajes de beto en la misma lección."""
    beto = user_id(db_session, "beto@demo.com")
    # Inscribir a beto para que pueda tener mensajes en la lección 1.
    db_session.add(Enrollment(user_id=beto, course_id=1))
    db_session.commit()

    # Beto tiene 2 mensajes.
    _seed_messages(db_session, "beto@demo.com", lesson_id=1, count=2)
    # Ana tiene 2 mensajes (vía chat para respetar el flujo normal).
    login(client, "ana@demo.com")
    client.post(CHAT_URL, json={"question": "pregunta de ana"})

    r = client.delete(DELETE_URL)
    assert r.status_code == 204

    # Solo quedan los mensajes de beto.
    remaining = db_session.scalars(
        select(Message.user_id)
    ).all()
    assert all(uid == beto for uid in remaining)


def test_delete_does_not_affect_messages_in_other_lesson(client, fake_ai, db_session):
    """Borrar la conversación en lesson 1 no toca los mensajes de ana en lesson 2."""
    ana = user_id(db_session, "ana@demo.com")
    db_session.add(Message(user_id=ana, lesson_id=2, role="user", content="en lección 2"))
    db_session.commit()

    login(client, "ana@demo.com")
    client.post(CHAT_URL, json={"question": "en lección 1"})

    r = client.delete(DELETE_URL)
    assert r.status_code == 204

    # El mensaje de lección 2 sigue intacto.
    remaining = db_session.scalars(select(Message)).all()
    assert len(remaining) == 1
    assert remaining[0].lesson_id == 2


def test_delete_unenrolled_user_gets_403_and_messages_intact(client, fake_ai, db_session):
    """Beto sin inscripción recibe 403 y los mensajes de ana siguen intactos."""
    ana = user_id(db_session, "ana@demo.com")
    db_session.add(Message(user_id=ana, lesson_id=1, role="user", content="de ana"))
    db_session.commit()

    login(client, "beto@demo.com")
    r = client.delete(DELETE_URL)
    assert r.status_code == 403
    assert count_messages(db_session) == 1  # el mensaje de ana sigue


def test_delete_without_session_returns_401(client, fake_ai):
    """Sin sesión: 401."""
    assert client.delete(DELETE_URL).status_code == 401


def test_delete_unknown_lesson_returns_404(client, fake_ai):
    """Lección inexistente: 404."""
    login(client, "ana@demo.com")
    assert client.delete("/lessons/999/messages").status_code == 404
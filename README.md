# Tutor virtual con IA y voz — POC

Prueba de concepto de una experiencia de aprendizaje asistida por IA integrada en un LMS. Un alumno inicia sesión, selecciona una lección, y puede preguntarle al tutor por escrito o por voz. El tutor responde únicamente con el contenido de la lección. El historial se recupera en visitas posteriores.

---

## Requisitos

- Python 3.11 o superior
- API key de [Google AI Studio](https://aistudio.google.com/apikey) (tier gratuito)
- Chrome o Edge para el dictado por voz (opcional; también funciona por texto)

---

## Configuración

Copia el archivo de variables de entorno y completa los valores:

```bash
cp .env.example .env
```

Edita `.env`:

```
SECRET_KEY=<cadena larga aleatoria, p. ej. la salida de: python -c "import secrets; print(secrets.token_hex(32))">
AI_API_KEY=<tu API key de Google AI Studio>
AI_MODEL=gemini-2.0-flash
```

Las demás variables tienen valores por defecto razonables (ver `.env.example`).

> **Importante:** `.env` está en `.gitignore` y nunca debe subirse al repositorio.

---

## Instalación

```bash
# Crea y activa el entorno virtual
python -m venv .venv
source .venv/bin/activate      # Linux / macOS
.venv\Scripts\activate         # Windows

# Instala dependencias
pip install -r requirements.txt
```

---

## Datos de prueba

El siguiente comando crea la base de datos, el curso, las lecciones y los dos alumnos de demo. Es idempotente: puede ejecutarse varias veces sin duplicar datos.

```bash
python seed.py
```

### Usuarios de prueba

| Email | Contraseña | Acceso |
|---|---|---|
| `ana@demo.com` | `demo1234` | Inscrita al curso |
| `beto@demo.com` | `demo1234` | Sin inscripción |

---

## Levantar la aplicación

```bash
uvicorn app.main:app --reload
```

Abre [http://localhost:8000](http://localhost:8000) en el navegador.

---

## Ejecutar los tests

Los tests no requieren conexión a internet ni API key real (la IA está mockeada):

```bash
pytest -v
```

Para ejecutar solo lint:

```bash
ruff check .
```

---

## Comprobar el flujo principal

1. Abre [http://localhost:8000](http://localhost:8000) e inicia sesión con `ana@demo.com` / `demo1234`.
2. Verás la lista de cursos a los que Ana tiene acceso.
3. Entra en una lección y escribe una pregunta, por ejemplo: **"¿Para qué sirve POST?"**
4. El tutor responde basándose únicamente en el contenido de la lección.
5. Pulsa 🔊 **Escuchar** para escuchar la respuesta en voz alta (Chrome/Edge).
6. Cierra sesión, vuelve a entrar y abre la misma lección: el historial se recupera.
7. Inicia sesión con `beto@demo.com` / `demo1234` e intenta acceder a `/lessons/1`: recibirás un **403**.

---

## Decisiones y límites

### Decisiones relevantes

**Stack mínimo sin framework de frontend.**
HTML + CSS + JS vanilla servido por FastAPI con Jinja2. Evita añadir complejidad de build y hace el código directamente legible en la demo.

**SQLite.**
Suficiente para una POC monousuario. Cambiar a PostgreSQL requeriría solo ajustar la URL de conexión en `config.py`.

**Cookie firmada con `itsdangerous`, sin tabla de sesiones.**
La firma criptográfica garantiza integridad sin almacenamiento en servidor. La expiración se valida en el servidor (`max_age` en `_serializer.loads`), no solo en el navegador. Límite conocido: el logout borra la cookie en el cliente, pero una cookie copiada sigue siendo válida hasta que expire. Aceptable para una POC; en producción se añadiría una lista de tokens revocados o sesiones en Redis.

**403 en lugar de 404 para lecciones sin acceso.**
Se elige 403 para claridad durante la demo. Un 404 evitaría revelar que la lección existe, lo que sería preferible en producción (se documenta en la sección de límites del README).

**Sin parámetro `next` en el login.**
La redirección tras el login siempre va a `/courses`, para evitar open redirects.

**Sin tabla de conversaciones.**
La conversación es el conjunto de mensajes de un alumno en una lección. No se necesita una entidad intermedia; la consulta `WHERE user_id = ? AND lesson_id = ?` es suficiente y más simple.

**Guardado atómico de pregunta y respuesta.**
Si la IA falla, no se guarda nada. El texto permanece en el cuadro y el alumno puede reintentar sin duplicar la pregunta en el historial. Si se guardara la pregunta antes de llamar a la IA, un reintento la duplicaría y quedarían preguntas sin respuesta.

**API key en cabecera `x-goog-api-key`, nunca en la URL.**
Las URLs aparecen en logs de servidores, proxies y herramientas de red. Una clave en la URL quedaría expuesta; en una cabecera no.

**Web Speech API del navegador.**
Sin coste, sin servidor adicional, sin datos que salgan de la infraestructura controlada (salvo la limitación descrita abajo). Limitación conocida: solo funciona bien en Chrome y Edge. Firefox no soporta `SpeechRecognition`; la app lo detecta y muestra un mensaje claro, permitiendo siempre escribir.

**Proveedor de IA intercambiable.**
Toda la lógica de llamada está en `app/ai.py`. Cambiar a Groq u otro proveedor requiere reescribir solo ese archivo.

**Prompt injection mitigado, no eliminado.**
Se delimitan los datos con etiquetas `<lesson>` y `<question>`, se neutralizan esas mismas etiquetas si aparecen en el texto del usuario o de la lección, y la instrucción de sistema indica ignorar órdenes embebidas. Verificado con pruebas reales. No es una garantía formal al 100 %.

### Límites conocidos (no desarrollado)

- **Sin registro de usuarios.** Los alumnos de prueba se crean con `seed.py`.
- **Sin roles ni panel de administración.** No hay interfaz para crear cursos o lecciones.
- **Sin token CSRF.** Mitigación básica con `SameSite=Lax`. Para producción se añadiría un token sincronizado.
- **Sin rate limiting por usuario.** La API de Gemini tiene sus propios límites; en producción se añadiría throttling en el backend.
- **Voz en Firefox no soportada.** `SpeechRecognition` no está disponible; la app lo informa y permite escribir.
- **`SpeechRecognition` en Chrome envía el audio a servidores de Google.** No se ejecuta localmente. Es un punto de privacidad a tener en cuenta.
- **Sesión sin estado en el servidor.** El logout no invalida una cookie ya copiada.
- **Latencia variable de Gemini.** En pruebas reales: de 0,7 s a casi 19 s. El timeout es configurable (`AI_TIMEOUT_SECONDS`, 30 s por defecto). El frontend permite reintentar.
- **Una sesión de BD abierta durante la llamada a la IA.** Aceptable para la POC; no escalaría con muchos usuarios concurrentes.
- **Los límites del tier gratuito de Gemini cambian.** Revisarlos en la [documentación del proveedor](https://ai.google.dev/gemini-api/docs/rate-limits) antes de la demo.

---

## Guion de demo

### 1. Flujo con acceso

1. Login con `ana@demo.com` / `demo1234`.
2. Mostrar la lista de cursos → entrar en la Lección 1.
3. Escribir: **"¿Para qué sirve POST?"** → mostrar la respuesta basada en el material.
4. Pulsar 🔊 **Escuchar** → el tutor lee la respuesta en voz alta.
5. Pulsar **Detener** para interrumpir.
6. Cerrar sesión → volver a entrar → abrir la misma lección → el historial aparece.

### 2. Flujo sin acceso

1. Login con `beto@demo.com` / `demo1234`.
2. Intentar navegar manualmente a `/lessons/1` → se recibe un **403** con página de error legible.
3. La misma URL con `Accept: application/json` devuelve `{"detail": "..."}` (para la API).

### 3. Pregunta fuera del material

1. Login con `ana@demo.com`.
2. Escribir: **"¿Cuál es la capital de Francia?"**
3. El tutor responde que eso no está cubierto en la lección, sin inventar.

### 4. Entrada por voz (Chrome/Edge)

1. Pulsar **🎤 Hablar** → el estado cambia a *Escuchando…*
2. Hacer una pregunta en voz alta.
3. El estado pasa a *Transcribiendo…* y el texto aparece en el cuadro.
4. Revisar el texto y pulsar **Enviar**.

### 5. Recuperación tras error

1. Desactivar la conexión a internet o poner un `AI_API_KEY` inválido.
2. Enviar una pregunta → el tutor muestra un error claro con botón **Reintentar**.
3. El texto de la pregunta permanece en el cuadro, listo para reintentar.
4. Restaurar la conexión o la clave → pulsar **Reintentar** → la respuesta llega.
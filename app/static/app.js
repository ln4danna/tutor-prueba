// Chat del tutor: estados, historial, envío, voz y borrado de conversación.
// Regla de seguridad: todo texto de usuario o de la IA se inserta con textContent, nunca innerHTML.
"use strict";

(() => {
  const chat = document.getElementById("chat");
  if (!chat) return;

  const lessonId = chat.dataset.lessonId;
  const MAX_LENGTH = 1000;

  const el = {
    status:       document.getElementById("chat-status"),
    statusText:   document.getElementById("chat-status-text"),
    messages:     document.getElementById("chat-messages"),
    error:        document.getElementById("chat-error"),
    errorText:    document.getElementById("chat-error-text"),
    errorAction:  document.getElementById("chat-error-action"),
    form:         document.getElementById("chat-form"),
    question:     document.getElementById("question"),
    charCount:    document.getElementById("char-count"),
    send:         document.getElementById("send-button"),
    mic:          document.getElementById("mic-button"),
    micLabel:     document.getElementById("mic-label"),
    micHint:      document.getElementById("mic-hint"),
    stopSpeaking: document.getElementById("stop-speaking"),
    clearBtn:     document.getElementById("clear-button"),
    dialog:       document.getElementById("clear-dialog"),
    dialogCancel: document.getElementById("clear-cancel"),
    dialogConfirm: document.getElementById("clear-confirm"),
  };

  // Capacidades del navegador (se declaran arriba para que todo el código las vea).
  const canSpeak = "speechSynthesis" in window && "SpeechSynthesisUtterance" in window;
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;

  // ---------------------------------------------------------------- Estados

  const STATUS_TEXT = {
    idle:         "Listo para tu pregunta",
    listening:    "Escuchando…",
    transcribing: "Transcribiendo…",
    thinking:     "El tutor está pensando…",
    speaking:     "Leyendo la respuesta…",
    error:        "Algo salió mal",
  };

  let state = "idle";
  let errorAction = null;

  function setState(next) {
    state = next;
    el.status.dataset.state = next;
    el.statusText.textContent = STATUS_TEXT[next];
    const busy = next === "thinking";
    el.send.disabled = busy;
    el.question.readOnly = busy;
    el.form.setAttribute("aria-busy", String(busy));
    // El micrófono solo se gestiona si el navegador soporta dictado;
    // si no, queda deshabilitado de forma permanente (ver más abajo).
    if (el.mic && Recognition) el.mic.disabled = busy;
    updateClearButton();
  }

  // ---------------------------------------------------------------- Error

  function showError(message, action = null) {
    el.errorText.textContent = message;
    errorAction = action;
    el.errorAction.hidden = !action;
    if (action) el.errorAction.textContent = action.label;
    el.error.hidden = false;
    setState("error");
  }

  function clearError() {
    el.error.hidden = true;
    errorAction = null;
    if (state === "error") setState("idle");
  }

  el.errorAction.addEventListener("click", () => {
    const action = errorAction;
    clearError();
    if (action) action.run();
  });

  // ---------------------------------------------------------------- API

  class ApiError extends Error {}

  /** fetch con Accept: application/json → 401 redirige al login, nunca recibe HTML. */
  async function api(url, options = {}) {
    let response;
    try {
      response = await fetch(url, {
        ...options,
        credentials: "same-origin",
        headers: { Accept: "application/json", ...(options.headers || {}) },
      });
    } catch {
      throw new ApiError("No hay conexión con el servidor. Revisa tu conexión e inténtalo de nuevo.");
    }

    if (response.status === 401) {
      window.location.assign("/login");
      throw new ApiError("Tu sesión expiró. Redirigiendo al inicio de sesión…");
    }

    let data = null;
    try { data = await response.json(); } catch { /* cuerpo vacío o 204 */ }

    if (!response.ok) {
      if (response.status === 403) throw new ApiError("No tienes acceso a esta lección.");
      if (response.status === 422) throw new ApiError(`La pregunta debe tener entre 1 y ${MAX_LENGTH} caracteres.`);
      const detail = data && typeof data.detail === "string" ? data.detail : null;
      throw new ApiError(detail || "Ocurrió un error en el servidor. Inténtalo de nuevo.");
    }
    return data;
  }

  // ---------------------------------------------------------------- Mensajes

  const timeFormat = new Intl.DateTimeFormat("es", { hour: "2-digit", minute: "2-digit" });

  /** ¿El usuario está al final de la lista (no está leyendo mensajes anteriores)? */
  function isScrolledToBottom() {
    const threshold = 60; // px de tolerancia
    return el.messages.scrollHeight - el.messages.scrollTop - el.messages.clientHeight < threshold;
  }

  function scrollToBottom(force = false) {
    if (force || isScrolledToBottom()) {
      el.messages.scrollTop = el.messages.scrollHeight;
    }
  }

  function renderMessage(message, { pending = false, thinking = false } = {}) {
    const item = document.createElement("li");
    item.className = thinking
      ? "message message--thinking"
      : `message message--${message.role}`;
    if (pending) item.classList.add("message--pending");

    if (!thinking) {
      const author = document.createElement("span");
      author.className = "message-author";
      author.textContent = message.role === "user" ? "Tú" : "Tutor";
      item.append(author);
    }

    const text = document.createElement("p");
    text.className = "message-text";
    text.textContent = thinking ? "Pensando…" : message.content; // nunca innerHTML
    if (thinking) text.setAttribute("aria-hidden", "true");
    item.append(text);

    if (!thinking) {
      const meta = document.createElement("div");
      meta.className = "message-meta";
      if (message.created_at) {
        const time = document.createElement("time");
        time.dateTime = message.created_at;
        time.textContent = timeFormat.format(new Date(message.created_at));
        meta.append(time);
      }
      if (message.input_mode === "voice" && message.role === "user") {
        const badge = document.createElement("span");
        badge.textContent = "🎤 por voz";
        meta.append(badge);
      }
      if (message.role === "assistant" && canSpeak) {
        const listen = document.createElement("button");
        listen.type = "button";
        listen.className = "btn btn-ghost btn-small listen-button";
        listen.textContent = "🔊 Escuchar";
        listen.setAttribute("aria-label", "Escuchar esta respuesta");
        listen.addEventListener("click", () => speak(message.content));
        meta.append(listen);
      }
      item.append(meta);
    }

    el.messages.append(item);
    return item;
  }

  function renderEmptyState() {
    const item = document.createElement("li");
    item.className = "messages-empty muted";
    item.id = "messages-empty";
    item.textContent = "Aún no hay preguntas. Escribe o graba la primera.";
    const example = document.createElement("span");
    example.className = "empty-example";
    example.textContent = "Ejemplo: ¿Para qué sirve POST?";
    item.append(example);
    el.messages.append(item);
  }

  async function loadHistory() {
    setState("thinking");
    el.statusText.textContent = "Cargando conversación…";
    try {
      const messages = await api(`/lessons/${lessonId}/messages`);
      el.messages.replaceChildren();
      if (messages.length === 0) renderEmptyState();
      messages.forEach((m) => renderMessage(m));
      scrollToBottom(true); // al cargar, siempre al final
      setState("idle");
    } catch (error) {
      showError(error.message, { label: "Reintentar", run: loadHistory });
    }
  }

  // ---------------------------------------------------------------- Botón borrar

  function updateClearButton() {
    const hasMessages = el.messages.querySelector(".message") !== null;
    el.clearBtn.disabled = !hasMessages || state === "thinking";
  }

  el.clearBtn.addEventListener("click", () => {
    // El <dialog> nativo gestiona el foco dentro del diálogo y la tecla ESC.
    el.dialog.showModal();
    el.dialogCancel.focus(); // foco inicial en Cancelar, la opción segura
  });

  el.dialogCancel.addEventListener("click", () => el.dialog.close());

  el.dialogConfirm.addEventListener("click", async () => {
    el.dialog.close();
    await doDeleteConversation();
  });

  // Al cerrar (Cancelar, Borrar o ESC) el foco vuelve al botón que abrió el diálogo,
  // siempre que siga habilitado.
  el.dialog.addEventListener("close", () => {
    if (!el.clearBtn.disabled) el.clearBtn.focus();
  });

  async function doDeleteConversation() {
    stopSpeaking();
    clearError();
    setState("thinking");
    try {
      await api(`/lessons/${lessonId}/messages`, { method: "DELETE" });
      el.messages.replaceChildren();
      renderEmptyState();
      setState("idle");
      el.question.focus(); // el botón queda deshabilitado: el foco pasa al campo de texto
    } catch (error) {
      showError(error.message, { label: "Reintentar", run: doDeleteConversation });
    }
  }

  // ---------------------------------------------------------------- Envío

  let inputMode = "text";

  function updateCharCount() {
    el.charCount.textContent = `${el.question.value.length}/${MAX_LENGTH}`;
  }

  /** Burbuja «Pensando…» provisional: se muestra mientras esperamos a la IA. */
  let thinkingBubble = null;

  function showThinkingBubble() {
    removeThinkingBubble();
    thinkingBubble = renderMessage({}, { thinking: true });
    scrollToBottom(true);
  }

  function removeThinkingBubble() {
    thinkingBubble?.remove();
    thinkingBubble = null;
  }

  async function sendQuestion() {
    const question = el.question.value.trim();
    if (!question) {
      showError("Escribe una pregunta antes de enviar.");
      el.question.focus();
      return;
    }
    if (question.length > MAX_LENGTH) {
      showError(`La pregunta debe tener como máximo ${MAX_LENGTH} caracteres.`);
      return;
    }

    clearError();
    stopSpeaking();
    document.getElementById("messages-empty")?.remove();
    setState("thinking");
    showThinkingBubble();

    try {
      const data = await api(`/lessons/${lessonId}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, input_mode: inputMode }),
      });
      removeThinkingBubble();
      renderMessage(data.question);
      renderMessage(data.answer);
      el.question.value = "";
      inputMode = "text";
      updateCharCount();
      scrollToBottom(true);
      setState("idle");
      el.question.focus();
    } catch (error) {
      // El texto sigue en el cuadro: reintentar no duplica la pregunta.
      removeThinkingBubble();
      if (!el.messages.querySelector(".message")) renderEmptyState();
      showError(error.message, { label: "Reintentar", run: sendQuestion });
    }
  }

  el.form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (state !== "thinking") sendQuestion();
  });

  el.question.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      el.form.requestSubmit();
    }
  });

  el.question.addEventListener("input", () => {
    inputMode = "text";
    updateCharCount();
    if (state === "error") clearError();
  });

  // ---------------------------------------------------------------- Texto a voz

  function pickSpanishVoice() {
    const voices = window.speechSynthesis.getVoices();
    return voices.find((v) => v.lang.toLowerCase().startsWith("es")) || null;
  }

  function speak(text) {
    if (!canSpeak) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "es-ES";
    const voice = pickSpanishVoice();
    if (voice) utterance.voice = voice;
    utterance.onstart = () => {
      clearError();
      setState("speaking");
      el.stopSpeaking.hidden = false;
    };
    utterance.onend = () => {
      el.stopSpeaking.hidden = true;
      if (state === "speaking") setState("idle");
    };
    utterance.onerror = (event) => {
      el.stopSpeaking.hidden = true;
      if (event.error === "interrupted" || event.error === "canceled") {
        if (state === "speaking") setState("idle");
        return;
      }
      showError("No se pudo reproducir la respuesta en voz alta. Puedes leerla en pantalla.");
    };
    window.speechSynthesis.speak(utterance);
  }

  function stopSpeaking() {
    if (!canSpeak) return;
    window.speechSynthesis.cancel();
    el.stopSpeaking.hidden = true;
    if (state === "speaking") setState("idle");
  }

  el.stopSpeaking.addEventListener("click", stopSpeaking);

  // ---------------------------------------------------------------- Voz a texto

  let recognition = null;

  const RECOGNITION_ERRORS = {
    "not-allowed":         "Permiso de micrófono denegado. Actívalo en la configuración del navegador o escribe tu pregunta.",
    "service-not-allowed": "El navegador no permite el dictado en esta página. Puedes escribir tu pregunta.",
    "audio-capture":       "No se detectó ningún micrófono. Conecta uno o escribe tu pregunta.",
    "no-speech":           "No te escuché. Pulsa «Volver a grabar» e inténtalo de nuevo.",
    network:               "El dictado necesita conexión a internet. Revisa tu conexión o escribe tu pregunta.",
  };

  function setMicListening(listening) {
    el.mic.setAttribute("aria-pressed", String(listening));
    el.mic.classList.toggle("is-listening", listening);
    el.micLabel.textContent = listening ? "Detener" : "Hablar";
  }

  function startRecognition() {
    if (!Recognition || state === "thinking") return;
    stopSpeaking();
    clearError();

    recognition = new Recognition();
    recognition.lang = "es-ES";
    recognition.interimResults = true;
    recognition.continuous = false;
    recognition.maxAlternatives = 1;

    const previousText = el.question.value;
    let transcript = "";
    let failed = false;

    recognition.onstart = () => {
      setMicListening(true);
      setState("listening");
    };

    recognition.onresult = (event) => {
      let finalText = "";
      let interimText = "";
      for (let i = 0; i < event.results.length; i += 1) {
        const piece = event.results[i][0].transcript;
        if (event.results[i].isFinal) finalText += piece;
        else interimText += piece;
      }
      transcript = (finalText || interimText).trim();
      el.question.value = transcript;
      updateCharCount();
      setState(finalText ? "listening" : "transcribing");
    };

    recognition.onerror = (event) => {
      if (event.error === "aborted") return;
      failed = true;
      const message = RECOGNITION_ERRORS[event.error] || "No se pudo usar el micrófono. Puedes escribir tu pregunta.";
      const canRetry = event.error === "no-speech" || event.error === "network";
      showError(message, canRetry ? { label: "Volver a grabar", run: startRecognition } : null);
    };

    recognition.onend = () => {
      setMicListening(false);
      recognition = null;
      if (failed) {
        if (!transcript) el.question.value = previousText;
        updateCharCount();
        return;
      }
      if (transcript) {
        // El alumno revisa la transcripción antes de enviar.
        inputMode = "voice";
        setState("idle");
        el.question.focus();
      } else {
        el.question.value = previousText;
        updateCharCount();
        showError(RECOGNITION_ERRORS["no-speech"], { label: "Volver a grabar", run: startRecognition });
      }
    };

    try {
      recognition.start();
    } catch {
      recognition = null;
      showError("No se pudo iniciar el micrófono. Inténtalo de nuevo o escribe tu pregunta.", {
        label: "Volver a grabar",
        run: startRecognition,
      });
    }
  }

  if (Recognition) {
    el.micHint.textContent = "Pulsa «Hablar», haz tu pregunta y revisa el texto antes de enviarlo.";
    el.mic.addEventListener("click", () => {
      if (recognition) recognition.stop();
      else startRecognition();
    });
  } else {
    el.mic.disabled = true;
    el.mic.title = "Dictado no disponible en este navegador";
    el.micHint.textContent =
      "Tu navegador no permite dictado por voz (funciona en Chrome y Edge). Puedes escribir tu pregunta.";
  }

  if (!canSpeak) {
    el.micHint.textContent += " La lectura en voz alta no está disponible en este navegador.";
  } else {
    // Chrome carga la lista de voces de forma diferida: pedirla pronto evita que la primera lectura use la voz por defecto.
    window.speechSynthesis.getVoices();
  }

  // El botón de detener lectura empieza oculto.
  el.stopSpeaking.hidden = true;

  // ---------------------------------------------------------------- Inicio

  updateCharCount();
  loadHistory();
})();
import os
import json
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("CENTRAL_DB_PATH", BASE_DIR / "central.db"))
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "")
REQUEST_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "60"))
OPENCLAW_BASE_URL = os.getenv("OPENCLAW_BASE_URL", "http://127.0.0.1:18789").rstrip("/")
OPENCLAW_TOKEN = os.getenv("OPENCLAW_TOKEN", "")
OPENCLAW_TIMEOUT_SECONDS = float(os.getenv("OPENCLAW_TIMEOUT_SECONDS", "15"))
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
TELEGRAM_ALLOWED_ADMIN_IDS = {
    item.strip() for item in os.getenv("TELEGRAM_ALLOWED_ADMIN_IDS", "").split(",") if item.strip()
}
CORRECTOR_MODEL = os.getenv("CORRECTOR_MODEL", DEFAULT_MODEL)
NOTION_API_TOKEN = os.getenv("NOTION_API_TOKEN", "")
NOTION_CONTENT_DB_ID = os.getenv("NOTION_CONTENT_DB_ID", "")
NOTION_VERSION = os.getenv("NOTION_VERSION", "2022-06-28")
BASEROW_BASE_URL = os.getenv("BASEROW_BASE_URL", "https://api.baserow.io").rstrip("/")
BASEROW_API_TOKEN = os.getenv("BASEROW_API_TOKEN", "")
BASEROW_TABLE_ID = os.getenv("BASEROW_TABLE_ID", "")
BASEROW_USER_FIELD_NAMES = os.getenv("BASEROW_USER_FIELD_NAMES", "true").lower() == "true"


WRITING_CORRECTION_PROMPT = """
Eres un corrector de writings en ingles para estudiantes hispanohablantes.

Objetivo:
- corregir el texto del estudiante
- explicar errores de forma clara y breve en espanol
- proponer una version mejorada en ingles natural

Responde SIEMPRE con este formato:
1. NIVEL ESTIMADO
2. ERRORES PRINCIPALES
3. TEXTO CORREGIDO
4. CONSEJOS BREVES

No inventes instrucciones del alumno. Si el texto es muy corto, indicalo con claridad.
""".strip()



EMAIL_CLASSIFICATION_PROMPT = """
Actuas como clasificador de correos para una bandeja de trabajo.

Tu trabajo es:
- resumir el correo en espanol en 1 o 2 frases
- clasificarlo en una sola categoria
- indicar tu confianza entre 0 y 1
- marcar si necesita revision humana

Categorias permitidas:
- newsletter
- factura
- cliente
- spam
- alerta
- otro

Devuelve SOLO JSON valido con este formato exacto:
{
  "summary": "resumen corto",
  "category": "newsletter|factura|cliente|spam|alerta|otro",
  "confidence": 0.0,
  "needs_review": false
}

Reglas:
- no devuelvas texto extra
- si dudas entre varias categorias, usa "otro"
- si la confianza es menor de 0.7, needs_review debe ser true
""".strip()


TELEGRAM_TASK_PROMPT = """
Actuas como asistente operativo del bot de Telegram Alert Blog Bot.

Tu trabajo es leer un bloque de texto libre y devolver una ficha corta y util para decidir que hacer con el contenido.

Clasifica SOLO en una de estas categorias:
- alerta
- idea
- tarea
- seguimiento
- otro

Prioridad permitida:
- alta
- media
- baja

Devuelve SOLO JSON valido con este formato exacto:
{
  "summary": "resumen corto en espanol",
  "category": "alerta|idea|tarea|seguimiento|otro",
  "priority": "alta|media|baja",
  "next_action": "siguiente paso sugerido en una frase",
  "needs_review": false
}

Reglas:
- resumen en 1 o 2 frases maximo
- no inventes datos que no aparezcan en el texto
- usa "otro" si el contenido no encaja bien
- usa needs_review=true si faltan datos, hay ambiguedad o la prioridad no esta clara
- no devuelvas texto fuera del JSON
""".strip()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_db_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    with get_db_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'manual',
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model TEXT NOT NULL,
                user_message TEXT NOT NULL,
                assistant_message TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS telegram_updates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_update_id TEXT,
                chat_id TEXT NOT NULL,
                user_id TEXT,
                username TEXT,
                chat_type TEXT NOT NULL,
                message_text TEXT NOT NULL,
                direction TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        # Evita procesar dos veces el mismo update entrante si Telegram reintenta el webhook.
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_telegram_updates_incoming_update_id
            ON telegram_updates (telegram_update_id)
            WHERE direction = 'in' AND telegram_update_id IS NOT NULL
            """
        )
        connection.commit()


class HealthResponse(BaseModel):
    status: str
    service: str
    ollama_base_url: str
    default_model: str | None
    timestamp: str


class OpenClawConfigResponse(BaseModel):
    enabled: bool
    base_url: str
    has_token: bool
    timeout_seconds: float
    control_ui_url: str


class OpenClawHealthResponse(BaseModel):
    status: str
    service: str
    openclaw_base_url: str
    gateway_status: str
    detail: str | None = None
    timestamp: str


class OpenClawPlanRequest(BaseModel):
    goal: str = Field(..., min_length=3, description="Objetivo o tarea que quieres llevar a OpenClaw")
    context: str | None = Field(
        default=None,
        description="Contexto adicional para acompañar el objetivo",
    )
    preferred_agent_id: str = Field(default="main", description="Agente preferido dentro de OpenClaw")
    preferred_model: str | None = Field(default=None, description="Modelo sugerido si quieres orientar la sesion")


class OpenClawPlanResponse(BaseModel):
    status: str
    gateway_live: bool
    openclaw_base_url: str
    control_ui_url: str
    preferred_agent_id: str
    preferred_model: str | None = None
    execution_mode: str
    next_step: str
    prompt: str
    timestamp: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="Mensaje del usuario")
    model: str | None = Field(default=None, description="Modelo opcional de Ollama")
    system_prompt: str | None = Field(
        default=None,
        description="Prompt de sistema opcional para orientar la respuesta",
    )


class ChatResponse(BaseModel):
    status: str
    model: str
    response: str
    created_at: str


class MemorySaveRequest(BaseModel):
    content: str = Field(..., min_length=1, description="Dato o recuerdo a guardar")
    source: str = Field(default="manual", description="Origen del recuerdo")


class MemoryItem(BaseModel):
    id: int
    content: str
    source: str
    created_at: str


class EchoRequest(BaseModel):
    text: str = Field(..., min_length=1)


class TelegramWebhookRequest(BaseModel):
    update_id: int | None = None
    message: dict[str, Any] | None = None
    channel_post: dict[str, Any] | None = None


class TelegramConfigResponse(BaseModel):
    enabled: bool
    has_bot_token: bool
    has_webhook_secret: bool
    admin_ids_configured: int
    corrector_model: str | None



class EmailProcessRequest(BaseModel):
    subject: str = Field(default="", description="Asunto del correo")
    sender: str = Field(..., min_length=3, description="Remitente del correo")
    received_date: str | None = Field(default=None, description="Fecha de recepcion del correo")
    body: str = Field(..., min_length=1, description="Cuerpo del correo")
    message_id: str | None = Field(default=None, description="ID unico del correo si existe")
    save_to_baserow: bool = Field(default=True, description="Si es true, intenta guardar el resultado en Baserow")
    model: str | None = Field(default=None, description="Modelo opcional de Ollama")


class EmailProcessResponse(BaseModel):
    status: str
    sender: str
    subject: str
    summary: str
    category: str
    confidence: float
    needs_review: bool
    model: str | None = None
    rule_applied: str | None = None
    saved_to_baserow: bool
    baserow_row_id: int | None = None
    created_at: str


class BaserowConfigResponse(BaseModel):
    enabled: bool
    base_url: str
    has_token: bool
    table_id: str | None
    user_field_names: bool


class NotionConfigResponse(BaseModel):
    enabled: bool
    has_token: bool
    has_database_id: bool
    database_id: str | None


class NotionIdeaItem(BaseModel):
    id: str
    idea: str
    descripcion: str | None = None
    tipo: str | None = None
    estado: str | None = None
    prioridad: str | None = None
    notas: str | None = None
    fecha: str | None = None
    notion_url: str | None = None



async def fetch_ollama_models() -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        response = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
        response.raise_for_status()
        payload = response.json()
        return payload.get("models", [])


async def generate_with_ollama(
    message: str, model: str | None = None, system_prompt: str | None = None
) -> tuple[str, str]:
    selected_model = model or DEFAULT_MODEL
    if not selected_model:
        models = await fetch_ollama_models()
        if not models:
            raise HTTPException(
                status_code=503,
                detail="No hay modelos disponibles en Ollama y OLLAMA_MODEL no esta configurado.",
            )
        selected_model = models[0]["name"]

    payload: dict[str, Any] = {
        "model": selected_model,
        "prompt": message,
        "stream": False,
    }
    if system_prompt:
        payload["system"] = system_prompt

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        try:
            response = await client.post(f"{OLLAMA_BASE_URL}/api/generate", json=payload)
            response.raise_for_status()
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=503,
                detail=f"No se pudo conectar con Ollama en {OLLAMA_BASE_URL}.",
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Ollama devolvio un error: {exc.response.text}",
            ) from exc

    data = response.json()
    return selected_model, data.get("response", "")


def normalize_email_category(value: str | None) -> str:
    allowed = {"newsletter", "factura", "cliente", "spam", "alerta", "otro"}
    normalized = (value or "").strip().lower()
    return normalized if normalized in allowed else "otro"


def normalize_task_category(value: str | None) -> str:
    allowed = {"alerta", "idea", "tarea", "seguimiento", "otro"}
    normalized = (value or "").strip().lower()
    return normalized if normalized in allowed else "otro"


def normalize_task_priority(value: str | None) -> str:
    allowed = {"alta", "media", "baja"}
    normalized = (value or "").strip().lower()
    return normalized if normalized in allowed else "media"


def compact_error_text(value: str, limit: int = 300) -> str:
    cleaned = " ".join(value.split())
    return cleaned[:limit]


def parse_confidence_value(value: Any, default: float = 0.0) -> float:
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        numeric_value = default
    return max(0.0, min(numeric_value, 1.0))


def rule_based_email_classification(subject: str, sender: str, body: str) -> dict[str, Any] | None:
    subject_lower = subject.lower()
    sender_lower = sender.lower()
    body_lower = body.lower()
    combined = f"{subject_lower}\n{sender_lower}\n{body_lower}"

    rules: list[tuple[str, tuple[str, ...], str, float, bool, str]] = [
        (
            "newsletter_linkedin",
            ("linkedin.com", "linkedin", "jobs-noreply@linkedin", "news@linkedin"),
            "newsletter",
            0.99,
            False,
            "Correo tipo newsletter o notificacion de LinkedIn.",
        ),
        (
            "factura_keywords",
            ("invoice", "factura", "receipt", "payment", "paypal", "stripe"),
            "factura",
            0.92,
            False,
            "Correo relacionado con pago, factura o recibo.",
        ),
        (
            "alerta_keywords",
            ("alert", "warning", "security", "critical", "incidencia", "error"),
            "alerta",
            0.88,
            False,
            "Correo de alerta tecnica o aviso importante.",
        ),
        (
            "spam_keywords",
            ("unsubscribe", "buy now", "limited time", "oferta exclusiva", "gana dinero"),
            "spam",
            0.82,
            True,
            "Correo promocional o sospechoso.",
        ),
    ]

    for rule_name, patterns, category, confidence, needs_review, summary in rules:
        if any(pattern in combined for pattern in patterns):
            return {
                "summary": summary,
                "category": category,
                "confidence": confidence,
                "needs_review": needs_review,
                "rule_applied": rule_name,
            }

    if any(token in sender_lower for token in ("client", "cliente", "@empresa", "@customer")):
        return {
            "summary": "Correo probablemente relacionado con un cliente o contacto directo.",
            "category": "cliente",
            "confidence": 0.75,
            "needs_review": True,
            "rule_applied": "client_sender_hint",
        }

    return None


async def classify_email_with_ollama(payload: EmailProcessRequest) -> tuple[str, dict[str, Any]]:
    message = (
        f"Subject: {payload.subject or 'Sin asunto'}\n"
        f"Sender: {payload.sender}\n"
        f"Received Date: {payload.received_date or 'Sin fecha'}\n\n"
        f"Body:\n{payload.body.strip()}"
    )
    model_used, raw_response = await generate_with_ollama(
        message=message,
        model=payload.model,
        system_prompt=EMAIL_CLASSIFICATION_PROMPT,
    )

    try:
        parsed = json.loads(raw_response)
    except json.JSONDecodeError:
        parsed = {
            "summary": raw_response.strip()[:400] or "No se pudo resumir el correo correctamente.",
            "category": "otro",
            "confidence": 0.2,
            "needs_review": True,
        }

    result = {
        "summary": str(parsed.get("summary", "")).strip() or "Sin resumen",
        "category": normalize_email_category(parsed.get("category")),
        "confidence": parse_confidence_value(parsed.get("confidence", 0.0)),
        "needs_review": bool(parsed.get("needs_review", True)),
        "rule_applied": None,
    }
    if result["confidence"] < 0.7:
        result["needs_review"] = True
    return model_used, result


async def classify_telegram_task(text: str) -> tuple[str, dict[str, Any]]:
    model_used, raw_response = await generate_with_ollama(
        message=text.strip(),
        system_prompt=TELEGRAM_TASK_PROMPT,
    )

    try:
        parsed = json.loads(raw_response)
    except json.JSONDecodeError:
        parsed = {
            "summary": raw_response.strip()[:400] or "No se pudo resumir el texto correctamente.",
            "category": "otro",
            "priority": "media",
            "next_action": "Revisar manualmente el contenido original.",
            "needs_review": True,
        }

    result = {
        "summary": str(parsed.get("summary", "")).strip() or "Sin resumen",
        "category": normalize_task_category(parsed.get("category")),
        "priority": normalize_task_priority(parsed.get("priority")),
        "next_action": str(parsed.get("next_action", "")).strip() or "Revisar manualmente el contenido original.",
        "needs_review": bool(parsed.get("needs_review", True)),
    }
    return model_used, result


async def save_email_to_baserow(payload: dict[str, Any]) -> dict[str, Any]:
    if not BASEROW_API_TOKEN or not BASEROW_TABLE_ID:
        raise HTTPException(
            status_code=503,
            detail="BASEROW_API_TOKEN o BASEROW_TABLE_ID no estan configurados.",
        )

    headers = {
        "Authorization": f"Token {BASEROW_API_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    params = {"user_field_names": str(BASEROW_USER_FIELD_NAMES).lower()}
    url = f"{BASEROW_BASE_URL}/api/database/rows/table/{BASEROW_TABLE_ID}/"

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        try:
            response = await client.post(url, headers=headers, params=params, json=payload)
            response.raise_for_status()
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=503,
                detail=f"No se pudo conectar con Baserow en {url}.",
            ) from exc
        except httpx.HTTPStatusError as exc:
            content_type = exc.response.headers.get("content-type", "")
            body_preview = compact_error_text(exc.response.text)
            if "text/html" in content_type.lower():
                detail = (
                    f"Baserow no devolvio JSON util. "
                    f"status={exc.response.status_code}, content_type={content_type}, url={url}, "
                    f"body_preview={body_preview}"
                )
            else:
                detail = (
                    f"Baserow devolvio un error. "
                    f"status={exc.response.status_code}, content_type={content_type or 'unknown'}, "
                    f"url={url}, body={body_preview}"
                )
            raise HTTPException(
                status_code=502,
                detail=detail,
            ) from exc
    return response.json()


async def fetch_openclaw_health() -> dict[str, Any]:
    headers: dict[str, str] = {}
    if OPENCLAW_TOKEN:
        headers["Authorization"] = f"Bearer {OPENCLAW_TOKEN}"

    async with httpx.AsyncClient(timeout=OPENCLAW_TIMEOUT_SECONDS) as client:
        try:
            response = await client.get(f"{OPENCLAW_BASE_URL}/health", headers=headers)
            response.raise_for_status()
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=503,
                detail=f"No se pudo conectar con OpenClaw en {OPENCLAW_BASE_URL}.",
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"OpenClaw devolvio un error: {exc.response.text}",
            ) from exc
    return response.json()


def build_openclaw_plan_prompt(payload: OpenClawPlanRequest) -> str:
    parts = [
        "Objetivo principal:",
        payload.goal.strip(),
    ]
    if payload.context:
        parts.extend(["", "Contexto adicional:", payload.context.strip()])
    if payload.preferred_model:
        parts.extend(["", f"Modelo sugerido: {payload.preferred_model.strip()}"])
    parts.extend(
        [
            "",
            "Trabaja paso a paso y prioriza una salida accionable.",
        ]
    )
    return "\n".join(parts)


async def telegram_api_request(method: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not TELEGRAM_BOT_TOKEN:
        raise HTTPException(status_code=503, detail="TELEGRAM_BOT_TOKEN no esta configurado.")

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        try:
            response = await client.post(url, json=payload)
            response.raise_for_status()
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=503,
                detail="No se pudo conectar con la API de Telegram.",
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Telegram devolvio un error: {exc.response.text}",
            ) from exc
    return response.json()


async def notion_api_request(method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    if not NOTION_API_TOKEN:
        raise HTTPException(status_code=503, detail="NOTION_API_TOKEN no esta configurado.")

    headers = {
        "Authorization": f"Bearer {NOTION_API_TOKEN}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }
    url = f"https://api.notion.com/v1{path}"

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        try:
            if method.upper() == "POST":
                response = await client.post(url, headers=headers, json=payload or {})
            elif method.upper() == "GET":
                response = await client.get(url, headers=headers)
            else:
                raise HTTPException(status_code=500, detail=f"Metodo Notion no soportado: {method}")
            response.raise_for_status()
        except httpx.RequestError as exc:
            raise HTTPException(status_code=503, detail="No se pudo conectar con la API de Notion.") from exc
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Notion devolvio un error: {exc.response.text}",
            ) from exc

    return response.json()


def extract_notion_text(value: Any) -> str | None:
    if not value:
        return None
    if isinstance(value, dict):
        if "title" in value:
            parts = value.get("title", [])
            return "".join(part.get("plain_text", "") for part in parts).strip() or None
        if "rich_text" in value:
            parts = value.get("rich_text", [])
            return "".join(part.get("plain_text", "") for part in parts).strip() or None
        if "select" in value and value.get("select"):
            return value["select"].get("name")
        if "status" in value and value.get("status"):
            return value["status"].get("name")
        if "date" in value and value.get("date"):
            return value["date"].get("start")
    return None


def parse_notion_idea(page: dict[str, Any]) -> NotionIdeaItem:
    properties = page.get("properties", {})
    return NotionIdeaItem(
        id=page.get("id", ""),
        idea=extract_notion_text(properties.get("Idea")) or extract_notion_text(properties.get("Name")) or "Sin titulo",
        descripcion=extract_notion_text(properties.get("Descripcion")) or extract_notion_text(properties.get("Descripción")),
        tipo=extract_notion_text(properties.get("Tipo")),
        estado=extract_notion_text(properties.get("Estado")),
        prioridad=extract_notion_text(properties.get("Prioridad")),
        notas=extract_notion_text(properties.get("Notas")),
        fecha=extract_notion_text(properties.get("Fecha")),
        notion_url=page.get("url"),
    )


async def fetch_notion_ideas(status: str = "Idea", limit: int = 10) -> list[NotionIdeaItem]:
    if not NOTION_CONTENT_DB_ID:
        raise HTTPException(status_code=503, detail="NOTION_CONTENT_DB_ID no esta configurado.")

    payload = {
        "page_size": max(limit * 3, 20),
        "sorts": [
            {
                "property": "Prioridad",
                "direction": "ascending",
            },
            {
                "property": "Fecha",
                "direction": "ascending",
            },
        ],
    }
    data = await notion_api_request("POST", f"/databases/{NOTION_CONTENT_DB_ID}/query", payload)
    ideas = [parse_notion_idea(page) for page in data.get("results", [])]

    def normalize_estado(value: str | None) -> str:
        if not value:
            return ""
        value = value.strip()
        if " " in value:
            value = value.split(" ", 1)[1]
        return value.lower()

    target = normalize_estado(status)
    filtered = [idea for idea in ideas if normalize_estado(idea.estado) == target]
    return filtered[:limit]



async def fetch_telegram_updates(offset: int | None = None, timeout_seconds: int = 30) -> list[dict[str, Any]]:
    payload: dict[str, Any] = {
        "timeout": timeout_seconds,
        "allowed_updates": ["message", "channel_post"],
    }
    if offset is not None:
        payload["offset"] = offset

    response = await telegram_api_request("getUpdates", payload)
    if not response.get("ok"):
        raise HTTPException(status_code=502, detail=f"Respuesta invalida de Telegram: {response}")
    return response.get("result", [])


def save_telegram_log(
    *,
    telegram_update_id: str | None,
    chat_id: str,
    user_id: str | None,
    username: str | None,
    chat_type: str,
    message_text: str,
    direction: str,
) -> None:
    with get_db_connection() as connection:
        connection.execute(
            """
            INSERT INTO telegram_updates (
                telegram_update_id, chat_id, user_id, username, chat_type, message_text, direction, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                telegram_update_id,
                chat_id,
                user_id,
                username,
                chat_type,
                message_text,
                direction,
                utc_now(),
            ),
        )
        connection.commit()


def has_processed_telegram_update(telegram_update_id: str | None) -> bool:
    if not telegram_update_id:
        return False

    with get_db_connection() as connection:
        row = connection.execute(
            """
            SELECT 1
            FROM telegram_updates
            WHERE telegram_update_id = ? AND direction = 'in'
            LIMIT 1
            """,
            (telegram_update_id,),
        ).fetchone()
    return row is not None


def is_admin_user(user_id: str | None) -> bool:
    return bool(user_id and user_id in TELEGRAM_ALLOWED_ADMIN_IDS)


async def send_telegram_message(chat_id: str, text: str) -> dict[str, Any]:
    return await telegram_api_request(
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": text[:4000],
        },
    )



async def correct_writing(student_text: str) -> tuple[str, str]:
    correction_request = (
        "Corrige el siguiente writing de un estudiante.\n\n"
        f"WRITING:\n{student_text.strip()}"
    )
    return await generate_with_ollama(
        message=correction_request,
        model=CORRECTOR_MODEL or None,
        system_prompt=WRITING_CORRECTION_PROMPT,
    )


async def handle_private_message(
    *,
    chat_id: str,
    user_id: str | None,
    username: str | None,
    text: str,
    telegram_update_id: str | None,
) -> dict[str, Any]:
    normalized = text.strip()

    if normalized.lower() in {"/start", "/help"}:
        reply_text = (
            "Hola. Soy AGENTE 2026 Telegram.\n\n"
            "Enviame un writing en ingles y te devolvere:\n"
            "1. nivel estimado\n"
            "2. errores principales\n"
            "3. texto corregido\n"
            "4. consejos breves\n\n"
            "Si eres admin, tambien puedes usar:\n"
            "/task texto o bloque"
        )
        await send_telegram_message(chat_id, reply_text)
        save_telegram_log(
            telegram_update_id=telegram_update_id,
            chat_id=chat_id,
            user_id=user_id,
            username=username,
            chat_type="private",
            message_text=reply_text,
            direction="out",
        )
        return {"status": "ok", "action": "help"}

    if normalized.lower().startswith("/task"):
        if not is_admin_user(user_id):
            reply_text = "No tienes permisos para usar /task."
            await send_telegram_message(chat_id, reply_text)
            save_telegram_log(
                telegram_update_id=telegram_update_id,
                chat_id=chat_id,
                user_id=user_id,
                username=username,
                chat_type="private",
                message_text=reply_text,
                direction="out",
            )
            return {"status": "ok", "action": "task_denied"}

        task_text = normalized[len("/task") :].strip()
        if not task_text:
            reply_text = (
                "Usa /task seguido del texto que quieres clasificar.\n\n"
                "Ejemplo:\n"
                "/task Cliente pide revisar landing y presupuesto antes del viernes."
            )
            await send_telegram_message(chat_id, reply_text)
            save_telegram_log(
                telegram_update_id=telegram_update_id,
                chat_id=chat_id,
                user_id=user_id,
                username=username,
                chat_type="private",
                message_text=reply_text,
                direction="out",
            )
            return {"status": "ok", "action": "task_usage"}

        model_used, task_result = await classify_telegram_task(task_text)
        review_text = "si" if task_result["needs_review"] else "no"
        reply_text = (
            "Ficha rapida\n\n"
            f"Resumen: {task_result['summary']}\n"
            f"Categoria: {task_result['category']}\n"
            f"Prioridad: {task_result['priority']}\n"
            f"Siguiente paso: {task_result['next_action']}\n"
            f"Revision manual: {review_text}\n"
            f"Modelo: {model_used}"
        )
        await send_telegram_message(chat_id, reply_text)
        save_telegram_log(
            telegram_update_id=telegram_update_id,
            chat_id=chat_id,
            user_id=user_id,
            username=username,
            chat_type="private",
            message_text=reply_text,
            direction="out",
        )
        return {"status": "ok", "action": "task_classified", "model": model_used}

    model_used, correction = await correct_writing(normalized)
    await send_telegram_message(chat_id, correction)
    save_telegram_log(
        telegram_update_id=telegram_update_id,
        chat_id=chat_id,
        user_id=user_id,
        username=username,
        chat_type="private",
        message_text=correction,
        direction="out",
    )
    return {"status": "ok", "action": "writing_corrected", "model": model_used}


async def handle_group_or_channel_message(
    *,
    chat_id: str,
    text: str,
    telegram_update_id: str | None,
) -> dict[str, Any]:
    normalized = text.strip()
    if normalized.lower() == "/help":
        reply_text = (
            "AGENTE 2026 Telegram activo.\n"
            "Usa el chat privado para enviar writings y recibir correcciones."
        )
        await send_telegram_message(chat_id, reply_text)
        save_telegram_log(
            telegram_update_id=telegram_update_id,
            chat_id=chat_id,
            user_id=None,
            username=None,
            chat_type="group",
            message_text=reply_text,
            direction="out",
        )
        return {"status": "ok", "action": "group_help"}

    return {"status": "ok", "action": "ignored_group_message"}


async def process_telegram_update(update: dict[str, Any]) -> dict[str, Any]:
    message = update.get("message") or update.get("channel_post")
    if not message:
        return {"status": "ignored", "reason": "unsupported_update_type"}

    text = (message.get("text") or "").strip()
    if not text:
        return {"status": "ignored", "reason": "empty_or_non_text_message"}

    chat = message.get("chat") or {}
    from_user = message.get("from") or {}
    chat_id = str(chat.get("id", ""))
    chat_type = str(chat.get("type", "unknown"))
    user_id = str(from_user.get("id")) if from_user.get("id") is not None else None
    username = from_user.get("username")
    update_id = str(update.get("update_id")) if update.get("update_id") is not None else None

    if has_processed_telegram_update(update_id):
        return {"status": "ignored", "reason": "duplicate_update"}

    try:
        save_telegram_log(
            telegram_update_id=update_id,
            chat_id=chat_id,
            user_id=user_id,
            username=username,
            chat_type=chat_type,
            message_text=text,
            direction="in",
        )
    except sqlite3.IntegrityError:
        return {"status": "ignored", "reason": "duplicate_update"}

    if chat_type == "private":
        return await handle_private_message(
            chat_id=chat_id,
            user_id=user_id,
            username=username,
            text=text,
            telegram_update_id=update_id,
        )

    if chat_type in {"group", "supergroup", "channel"}:
        return await handle_group_or_channel_message(
            chat_id=chat_id,
            text=text,
            telegram_update_id=update_id,
        )

    return {"status": "ignored", "reason": f"unsupported_chat_type:{chat_type}"}


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="API CENTRAL",
    version="0.1.0",
    description="Central base con FastAPI, memoria local y conexion a Ollama.",
    lifespan=lifespan,
)


@app.get("/", tags=["system"])
def root() -> dict[str, str]:
    return {
        "service": "API CENTRAL",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="API CENTRAL",
        ollama_base_url=OLLAMA_BASE_URL,
        default_model=DEFAULT_MODEL or None,
        timestamp=utc_now(),
    )


@app.get("/openclaw/config", response_model=OpenClawConfigResponse, tags=["openclaw"])
def openclaw_config() -> OpenClawConfigResponse:
    return OpenClawConfigResponse(
        enabled=bool(os.getenv("OPENCLAW_BASE_URL") or OPENCLAW_TOKEN),
        base_url=OPENCLAW_BASE_URL,
        has_token=bool(OPENCLAW_TOKEN),
        timeout_seconds=OPENCLAW_TIMEOUT_SECONDS,
        control_ui_url=OPENCLAW_BASE_URL or "",
    )


@app.get("/baserow/config", response_model=BaserowConfigResponse, tags=["baserow"])
def baserow_config() -> BaserowConfigResponse:
    return BaserowConfigResponse(
        enabled=bool(BASEROW_API_TOKEN and BASEROW_TABLE_ID),
        base_url=BASEROW_BASE_URL,
        has_token=bool(BASEROW_API_TOKEN),
        table_id=BASEROW_TABLE_ID or None,
        user_field_names=BASEROW_USER_FIELD_NAMES,
    )


@app.get("/openclaw/health", response_model=OpenClawHealthResponse, tags=["openclaw"])
async def openclaw_health() -> OpenClawHealthResponse:
    health_payload = await fetch_openclaw_health()
    return OpenClawHealthResponse(
        status="ok",
        service="API CENTRAL",
        openclaw_base_url=OPENCLAW_BASE_URL,
        gateway_status=str(health_payload.get("status", "unknown")),
        detail=health_payload.get("detail"),
        timestamp=utc_now(),
    )


@app.post("/openclaw/plan", response_model=OpenClawPlanResponse, tags=["openclaw"])
async def openclaw_plan(payload: OpenClawPlanRequest) -> OpenClawPlanResponse:
    gateway_live = False
    try:
        health_payload = await fetch_openclaw_health()
        gateway_live = bool(health_payload.get("ok")) or str(health_payload.get("status", "")).lower() == "live"
    except HTTPException:
        gateway_live = False

    return OpenClawPlanResponse(
        status="ok",
        gateway_live=gateway_live,
        openclaw_base_url=OPENCLAW_BASE_URL,
        control_ui_url=OPENCLAW_BASE_URL,
        preferred_agent_id=payload.preferred_agent_id,
        preferred_model=payload.preferred_model,
        execution_mode="manual_handoff_to_openclaw",
        next_step=(
            "Abrir OpenClaw Control y pegar este prompt en el agente indicado."
            if gateway_live
            else "Levantar o revisar OpenClaw antes de usar este prompt."
        ),
        prompt=build_openclaw_plan_prompt(payload),
        timestamp=utc_now(),
    )


@app.post("/email/process", response_model=EmailProcessResponse, tags=["email"])
async def email_process(payload: EmailProcessRequest) -> EmailProcessResponse:
    rule_result = rule_based_email_classification(payload.subject, payload.sender, payload.body)
    model_used: str | None = None

    if rule_result:
        classification = rule_result
    else:
        model_used, classification = await classify_email_with_ollama(payload)

    baserow_row_id: int | None = None
    saved_to_baserow = False
    if payload.save_to_baserow and BASEROW_API_TOKEN and BASEROW_TABLE_ID:
        baserow_payload = {
            "Subject": payload.subject or "",
            "Sender": payload.sender,
            "Received Date": payload.received_date or utc_now(),
            "Summary": classification["summary"],
            "Category": classification["category"],
            "Confidence": classification["confidence"],
            "Needs Review": classification["needs_review"],
            "Message ID": payload.message_id or "",
            "Raw Preview": payload.body.strip()[:500],
            "Status": "processed",
        }
        row = await save_email_to_baserow(baserow_payload)
        baserow_row_id = row.get("id")
        saved_to_baserow = True

    return EmailProcessResponse(
        status="ok",
        sender=payload.sender,
        subject=payload.subject,
        summary=classification["summary"],
        category=classification["category"],
        confidence=classification["confidence"],
        needs_review=classification["needs_review"],
        model=model_used,
        rule_applied=classification.get("rule_applied"),
        saved_to_baserow=saved_to_baserow,
        baserow_row_id=baserow_row_id,
        created_at=utc_now(),
    )


@app.get("/test", tags=["system"])
def test() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/models", tags=["ollama"])
async def models() -> dict[str, Any]:
    try:
        available_models = await fetch_ollama_models()
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"No se pudo conectar con Ollama en {OLLAMA_BASE_URL}.",
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Ollama devolvio un error: {exc.response.text}",
        ) from exc

    return {
        "status": "ok",
        "ollama_base_url": OLLAMA_BASE_URL,
        "default_model": DEFAULT_MODEL or None,
        "models": available_models,
    }


@app.post("/chat", response_model=ChatResponse, tags=["ollama"])
async def chat(payload: ChatRequest) -> ChatResponse:
    selected_model, assistant_message = await generate_with_ollama(
        message=payload.message,
        model=payload.model,
        system_prompt=payload.system_prompt,
    )
    created_at = utc_now()

    with get_db_connection() as connection:
        connection.execute(
            """
            INSERT INTO chat_logs (model, user_message, assistant_message, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (selected_model, payload.message, assistant_message, created_at),
        )
        connection.commit()

    return ChatResponse(
        status="ok",
        model=selected_model,
        response=assistant_message,
        created_at=created_at,
    )


@app.post("/memory/save", response_model=MemoryItem, tags=["memory"])
def memory_save(payload: MemorySaveRequest) -> MemoryItem:
    created_at = utc_now()
    with get_db_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO memories (content, source, created_at)
            VALUES (?, ?, ?)
            """,
            (payload.content, payload.source, created_at),
        )
        connection.commit()
        memory_id = cursor.lastrowid

    return MemoryItem(
        id=memory_id,
        content=payload.content,
        source=payload.source,
        created_at=created_at,
    )


@app.get("/memory/list", response_model=list[MemoryItem], tags=["memory"])
def memory_list(limit: int = 20) -> list[MemoryItem]:
    safe_limit = min(max(limit, 1), 100)
    with get_db_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, content, source, created_at
            FROM memories
            ORDER BY id DESC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()

    return [MemoryItem(**dict(row)) for row in rows]


@app.get("/chat/history", tags=["memory"])
def chat_history(limit: int = 20) -> dict[str, Any]:
    safe_limit = min(max(limit, 1), 100)
    with get_db_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, model, user_message, assistant_message, created_at
            FROM chat_logs
            ORDER BY id DESC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()

    return {
        "status": "ok",
        "items": [dict(row) for row in rows],
    }


@app.post("/tools/echo", tags=["tools"])
def tools_echo(payload: EchoRequest) -> dict[str, str]:
    return {
        "status": "ok",
        "echo": payload.text,
        "timestamp": utc_now(),
    }


@app.get("/telegram/config", response_model=TelegramConfigResponse, tags=["telegram"])
def telegram_config() -> TelegramConfigResponse:
    return TelegramConfigResponse(
        enabled=bool(TELEGRAM_BOT_TOKEN),
        has_bot_token=bool(TELEGRAM_BOT_TOKEN),
        has_webhook_secret=bool(TELEGRAM_WEBHOOK_SECRET),
        admin_ids_configured=len(TELEGRAM_ALLOWED_ADMIN_IDS),
        corrector_model=CORRECTOR_MODEL or None,
    )




@app.get("/notion/config", response_model=NotionConfigResponse, tags=["notion"])
def notion_config() -> NotionConfigResponse:
    return NotionConfigResponse(
        enabled=bool(NOTION_API_TOKEN and NOTION_CONTENT_DB_ID),
        has_token=bool(NOTION_API_TOKEN),
        has_database_id=bool(NOTION_CONTENT_DB_ID),
        database_id=NOTION_CONTENT_DB_ID or None,
    )


@app.get("/notion/ideas", response_model=list[NotionIdeaItem], tags=["notion"])
async def notion_ideas(status: str = "Idea", limit: int = 10) -> list[NotionIdeaItem]:
    safe_limit = min(max(limit, 1), 20)
    return await fetch_notion_ideas(status=status, limit=safe_limit)




@app.post("/telegram/webhook", tags=["telegram"])
async def telegram_webhook(
    payload: TelegramWebhookRequest,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, Any]:
    if TELEGRAM_WEBHOOK_SECRET and x_telegram_bot_api_secret_token != TELEGRAM_WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Secret token de Telegram invalido.")
    update = payload.model_dump(exclude_none=True)
    return await process_telegram_update(update)




import os
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from services.notion_mcp import get_notion_mcp_config
from services.openclaw import get_openclaw_config
from services.transcriber import get_transcriber_config


BASE_DIR = Path(__file__).resolve().parent


def load_env_file(path: Path) -> None:
    if not path.is_file():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        os.environ.setdefault(key, value)


load_env_file(BASE_DIR / "env")
load_env_file(BASE_DIR / ".env")

DB_PATH = Path(os.getenv("CENTRAL_DB_PATH", BASE_DIR / "central.db"))
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "")
REQUEST_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "60"))
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
TELEGRAM_ALLOWED_ADMIN_IDS = {
    item.strip() for item in os.getenv("TELEGRAM_ALLOWED_ADMIN_IDS", "").split(",") if item.strip()
}
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID", "")
CORRECTOR_MODEL = os.getenv("CORRECTOR_MODEL", DEFAULT_MODEL)
NOTION_API_TOKEN = os.getenv("NOTION_API_TOKEN", "")
NOTION_CONTENT_DB_ID = os.getenv("NOTION_CONTENT_DB_ID", "")
NOTION_VERSION = os.getenv("NOTION_VERSION", "2022-06-28")
OPENCLAW_BASE_URL = os.getenv("OPENCLAW_BASE_URL", "")
OPENCLAW_API_KEY = os.getenv("OPENCLAW_API_KEY", "")
NOTION_MCP_URL = os.getenv("NOTION_MCP_URL", "")
NOTION_MCP_API_KEY = os.getenv("NOTION_MCP_API_KEY", "")
TRANSCRIBER_PROVIDER = os.getenv("TRANSCRIBER_PROVIDER", "")
TRANSCRIBER_MODEL = os.getenv("TRANSCRIBER_MODEL", "")
TRANSCRIBER_API_KEY = os.getenv("TRANSCRIBER_API_KEY", "")


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


QUICKINGLES_DRAFT_PROMPT = """
Actuas como asistente editorial del canal de Telegram "Quickinglés".

Tu trabajo NO es escribir articulos largos ni textos genericos sobre aprender ingles.
Tu trabajo es crear posts cortos, visuales, didacticos y publicables en Telegram.

ESTILO DEL CANAL
- tono claro, cercano y practico
- foco en ingles real y util
- explicaciones muy faciles de escanear
- nada de relleno, nada de motivacion vacia, nada de sonar a blog
- debe parecer contenido hecho para alumnos reales que quieren mejorar su ingles

FORMATO DESEADO
- titulo corto con emoji
- una etiqueta o subtitulo corto tipo categoria
- explicacion central breve
- ejemplos en ingles con traduccion usando este formato:
  Example:
  "texto en ingles"
  -> traduccion
- un bloque extra tipo "English Boost", "3 ejemplos utiles" o "Mini reto" cuando encaje
- cierre con firma exacta:
  Jesus | Quickinglés

REGLAS IMPORTANTES
- no hagas posts demasiado largos
- prioriza claridad y utilidad real
- usa emojis con moderacion
- si el tema compara dos expresiones, deja muy clara la diferencia
- si el tema es de error comun, explica el error y da la forma correcta
- evita listas eternas
- evita frases como "en el mundo digital de hoy" o cualquier tono generico
- no menciones IA ni metodologia salvo que el tema vaya de eso

OBJETIVO FINAL
Entregar un borrador listo para pegar en Telegram, con estilo Quickinglés, no un esquema ni una explicacion para el creador.

Si falta contexto, usa la idea principal y conviertela en un borrador util, breve y publicable.
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
        connection.commit()


class HealthResponse(BaseModel):
    status: str
    service: str
    ollama_base_url: str
    default_model: str | None
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
    has_channel_id: bool
    admin_ids_configured: int
    corrector_model: str | None


class TelegramChannelContentRequest(BaseModel):
    topic: str = Field(..., min_length=3, description="Tema principal del post")
    angle: str | None = Field(default=None, description="Enfoque concreto del contenido")
    audience: str = Field(
        default="estudiantes hispanohablantes que quieren mejorar su ingles real",
        description="Publico objetivo del contenido",
    )
    objective: str | None = Field(default=None, description="Objetivo del post")
    content_type: str = Field(default="telegram_post", description="Tipo de pieza a generar")
    extra_notes: str | None = Field(default=None, description="Notas adicionales para el borrador")
    include_cta: bool = Field(default=False, description="Si quieres una llamada a la accion breve")
    model: str | None = Field(default=None, description="Modelo opcional de Ollama")
    publish: bool = Field(default=False, description="Si es true, publica el borrador en el canal")


class TelegramChannelContentResponse(BaseModel):
    status: str
    model: str
    draft: str
    published: bool
    channel_id: str | None = None
    telegram_message_id: int | None = None
    created_at: str


class NotionConfigResponse(BaseModel):
    enabled: bool
    has_token: bool
    has_database_id: bool
    database_id: str | None


class OpenClawConfigResponse(BaseModel):
    enabled: bool
    base_url: str | None
    has_api_key: bool


class NotionMcpConfigResponse(BaseModel):
    enabled: bool
    url: str | None
    has_api_key: bool


class TranscriberConfigResponse(BaseModel):
    enabled: bool
    provider: str | None
    model: str | None
    has_api_key: bool


class TranscriptionRequest(BaseModel):
    audio_source: str = Field(..., min_length=3, description="Ruta, URL o identificador del audio")
    language: str | None = Field(default=None, description="Idioma esperado del audio")


class NotionIdeaItem(BaseModel):
    id: str
    idea: str
    descripcion: str | None = None
    tipo: str | None = None
    estado: str | None = None
    prioridad: str | None = None
    canal: str | None = None
    notas: str | None = None
    fecha: str | None = None
    notion_url: str | None = None


class NotionDraftsRequest(BaseModel):
    limit: int = Field(default=3, ge=1, le=10)
    status: str = Field(default="Idea")
    model: str | None = None


class NotionDraftItem(BaseModel):
    idea: NotionIdeaItem
    model: str
    draft: str


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
        canal=extract_notion_text(properties.get("Canal")),
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


async def build_quickingles_draft(idea: NotionIdeaItem, model: str | None = None) -> tuple[str, str]:
    message = (
        f"Tema principal: {idea.idea}\n\n"
        f"Descripcion: {idea.descripcion or 'Sin descripcion'}\n"
        f"Tipo: {idea.tipo or 'No definido'}\n"
        f"Canal: {idea.canal or 'Quickinglés'}\n"
        f"Notas: {idea.notas or 'Sin notas adicionales'}\n"
        "Genera un borrador listo para Telegram siguiendo el estilo Quickinglés."
    )
    return await generate_with_ollama(
        message=message,
        model=model,
        system_prompt=QUICKINGLES_DRAFT_PROMPT,
    )


def build_telegram_channel_prompt(payload: TelegramChannelContentRequest) -> str:
    cta_instruction = (
        "Incluye una llamada a la accion final muy breve y natural."
        if payload.include_cta
        else "No incluyas llamada a la accion final salvo que encaje de forma muy natural."
    )
    return (
        f"Tema principal: {payload.topic}\n"
        f"Angulo: {payload.angle or 'Elige el enfoque mas util y claro para Telegram'}\n"
        f"Audiencia: {payload.audience}\n"
        f"Objetivo: {payload.objective or 'Aportar valor practico y publicable en el canal'}\n"
        f"Tipo de contenido: {payload.content_type}\n"
        f"Notas extra: {payload.extra_notes or 'Sin notas extra'}\n"
        f"{cta_instruction}\n"
        "Devuelve un borrador final listo para publicar en Telegram."
    )


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


async def publish_to_channel(text: str) -> dict[str, Any]:
    if not TELEGRAM_CHANNEL_ID:
        raise HTTPException(status_code=503, detail="TELEGRAM_CHANNEL_ID no esta configurado.")
    return await send_telegram_message(TELEGRAM_CHANNEL_ID, text)


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
            "/publish texto"
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

    if normalized.lower().startswith("/publish"):
        if not is_admin_user(user_id):
            reply_text = "No tienes permisos para publicar en el canal."
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
            return {"status": "ok", "action": "publish_denied"}

        publish_text = normalized[len("/publish") :].strip()
        if not publish_text:
            reply_text = "Usa /publish seguido del texto que quieres enviar al canal."
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
            return {"status": "ok", "action": "publish_usage"}

        await publish_to_channel(publish_text)
        reply_text = "Contenido publicado en el canal."
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
        return {"status": "ok", "action": "publish_success"}

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

    save_telegram_log(
        telegram_update_id=update_id,
        chat_id=chat_id,
        user_id=user_id,
        username=username,
        chat_type=chat_type,
        message_text=text,
        direction="in",
    )

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


@app.get("/openclaw/config", response_model=OpenClawConfigResponse, tags=["openclaw"])
def openclaw_config() -> OpenClawConfigResponse:
    config = get_openclaw_config()
    return OpenClawConfigResponse(**config)


@app.get("/notion/mcp/config", response_model=NotionMcpConfigResponse, tags=["notion"])
def notion_mcp_config() -> NotionMcpConfigResponse:
    config = get_notion_mcp_config()
    return NotionMcpConfigResponse(**config)


@app.get("/transcriber/config", response_model=TranscriberConfigResponse, tags=["transcriber"])
def transcriber_config() -> TranscriberConfigResponse:
    config = get_transcriber_config()
    return TranscriberConfigResponse(**config)


@app.post("/transcriber/transcribe", tags=["transcriber"])
def transcriber_transcribe(payload: TranscriptionRequest) -> dict[str, Any]:
    config = get_transcriber_config()
    if not config["enabled"]:
        raise HTTPException(status_code=503, detail="TRANSCRIBER_PROVIDER no esta configurado.")

    raise HTTPException(
        status_code=501,
        detail=(
            "El conector de transcripcion aun es un esqueleto. "
            "Podemos enchufar Whisper, faster-whisper u otro proveedor en la siguiente iteracion."
        ),
    )


@app.get("/telegram/config", response_model=TelegramConfigResponse, tags=["telegram"])
def telegram_config() -> TelegramConfigResponse:
    return TelegramConfigResponse(
        enabled=bool(TELEGRAM_BOT_TOKEN),
        has_bot_token=bool(TELEGRAM_BOT_TOKEN),
        has_webhook_secret=bool(TELEGRAM_WEBHOOK_SECRET),
        has_channel_id=bool(TELEGRAM_CHANNEL_ID),
        admin_ids_configured=len(TELEGRAM_ALLOWED_ADMIN_IDS),
        corrector_model=CORRECTOR_MODEL or None,
    )


@app.post(
    "/telegram/channel/content",
    response_model=TelegramChannelContentResponse,
    tags=["telegram"],
)
async def telegram_channel_content(
    payload: TelegramChannelContentRequest,
) -> TelegramChannelContentResponse:
    prompt = build_telegram_channel_prompt(payload)
    model_used, draft = await generate_with_ollama(
        message=prompt,
        model=payload.model,
        system_prompt=QUICKINGLES_DRAFT_PROMPT,
    )

    published = False
    telegram_message_id: int | None = None
    if payload.publish:
        telegram_response = await publish_to_channel(draft)
        published = bool(telegram_response.get("ok"))
        result = telegram_response.get("result") or {}
        telegram_message_id = result.get("message_id")

    return TelegramChannelContentResponse(
        status="ok",
        model=model_used,
        draft=draft,
        published=published,
        channel_id=TELEGRAM_CHANNEL_ID or None,
        telegram_message_id=telegram_message_id,
        created_at=utc_now(),
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


@app.post("/notion/ideas/drafts", response_model=list[NotionDraftItem], tags=["notion"])
async def notion_ideas_drafts(payload: NotionDraftsRequest) -> list[NotionDraftItem]:
    ideas = await fetch_notion_ideas(status=payload.status, limit=payload.limit)
    drafts: list[NotionDraftItem] = []
    for idea in ideas:
        model_used, draft = await build_quickingles_draft(idea, model=payload.model)
        drafts.append(NotionDraftItem(idea=idea, model=model_used, draft=draft))
    return drafts


@app.post("/telegram/webhook", tags=["telegram"])
async def telegram_webhook(
    payload: TelegramWebhookRequest,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, Any]:
    if TELEGRAM_WEBHOOK_SECRET and x_telegram_bot_api_secret_token != TELEGRAM_WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Secret token de Telegram invalido.")
    update = payload.model_dump(exclude_none=True)
    return await process_telegram_update(update)
